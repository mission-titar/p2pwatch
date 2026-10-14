"""One client's searches: a task's search, its observations recorded, and the backoff a failure
earns, per client when unreachable and per channel when refused (stage 2, D4 and D7)."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from catalog_matching.engine import MatchingEngine
from p2pwatch.application.record_observations import record_observation
from p2pwatch.domain.observability.events import (
    ClientUnreachable,
    SearchExecuted,
    SearchFailed,
)
from p2pwatch.domain.observation import FileObservation
from p2pwatch.domain.search.backoff import backoff_delay
from p2pwatch.ports.catalog_repository import CatalogRepository
from p2pwatch.ports.client_errors import ClientUnreachableError, SearchFailedError
from p2pwatch.ports.clock import WallClock
from p2pwatch.ports.rng import Rng
from p2pwatch.ports.scheduler_state_repository import BackoffKey, BackoffState
from p2pwatch.ports.search_client import SearchClient
from p2pwatch.ports.telemetry import Telemetry
from p2pwatch.ports.wake_hub import WakeHub

_logger = logging.getLogger("p2pwatch.application.search_worker")

# A ceiling, not a duration: above Kad's 45 s and an ed2k sweep, it guards a search never ending.
SEARCH_BUDGET_SECONDS = 120.0


def _iso(moment: datetime) -> str:
    """Fixed-width ISO-8601 UTC (microseconds ALWAYS written) - same rules as the adapter's
    ``utc_iso`` (which we cannot import: dependency rule §4) so that the
    PERSISTED format is identical to the other timestamps'."""
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class SearchTask:
    """A unit of work: a keyword on a channel (spec §4)."""

    keyword: str
    channel: str


@dataclass(frozen=True)
class BackoffPolicy:
    """The backoff's parameters, as PRIMITIVES (spec §5; injected by composition).

    ``jitter_ratio``: fraction of the nominal delay drawn as additional jitter
    (anti-thundering-herd, spec §3) - e.g. 0.3 ⇒ jitter in ``[0, 0.3 * delay)``.
    """

    base_seconds: float
    cap_seconds: float
    factor: float
    jitter_ratio: float


class BackoffRegistry:
    """SHARED backoff registry keyed by :class:`BackoffKey`, PERSISTABLE.

    Holds a map ``backoff_key → BackoffState(attempts, retry_after)`` (spec §3/§7). ``retry_after``
    is computed on failure: ``wall_clock.now() + backoff_delay(attempts) + jitter`` (jitter drawn
    from the ``Rng`` port, deterministic in test) → fixed-width ISO-8601 UTC. ``is_in_backoff``
    skips a key while ``now < retry_after``. ``snapshot``/``load_from`` bridge to
    ``scheduler_state`` (the persistence survives a restart).
    """

    def __init__(self, policy: BackoffPolicy, wall_clock: WallClock, rng: Rng) -> None:
        self._policy = policy
        self._wall_clock = wall_clock
        self._rng = rng
        self._state_by_key: dict[BackoffKey, BackoffState] = {}

    def load_from(self, states: dict[BackoffKey, BackoffState]) -> None:
        """Reloads the registry from a persisted snapshot (recovery after crash, spec §7)."""
        self._state_by_key = dict(states)

    def snapshot(self) -> dict[BackoffKey, BackoffState]:
        """Copy of the current map (to persist, spec §7)."""
        return dict(self._state_by_key)

    def is_in_backoff(self, backoff_key: BackoffKey) -> bool:
        """``True`` if ``backoff_key`` has a ``retry_after`` still in the FUTURE (to skip)."""
        return self.seconds_remaining(backoff_key) > 0

    def seconds_remaining(self, backoff_key: BackoffKey) -> float:
        """Seconds until ``backoff_key``'s ``retry_after``, 0 when it has none or it has passed."""
        state = self._state_by_key.get(backoff_key)
        if state is None:
            return 0.0
        left = datetime.fromisoformat(state.retry_after) - self._wall_clock.now()
        return max(0.0, left.total_seconds())

    def record_failure(self, backoff_key: BackoffKey) -> float:
        """Increments ``attempts``, computes delay+jitter, sets ``retry_after``. Returns the delay.

        The delay is for the LOG; the operational decision is the ``retry_after`` (skip).
        """
        if self.is_in_backoff(backoff_key):  # a concurrent search started before it: same round
            return self.seconds_remaining(backoff_key)
        attempts = (
            self._state_by_key[backoff_key].attempts + 1 if backoff_key in self._state_by_key else 1
        )
        delay = backoff_delay(
            attempts,
            base=self._policy.base_seconds,
            cap=self._policy.cap_seconds,
            factor=self._policy.factor,
        )
        delay += self._rng.jitter(self._policy.jitter_ratio * delay)
        retry_after = _iso(self._wall_clock.now() + timedelta(seconds=delay))
        self._state_by_key[backoff_key] = BackoffState(attempts=attempts, retry_after=retry_after)
        return delay

    def reset(self, backoff_key: BackoffKey) -> None:
        """Clears the backoff of a key (success)."""
        self._state_by_key.pop(backoff_key, None)


@dataclass
class WorkerDeps:
    """A worker's shared dependencies (composition assembles them once).

    ``backoff`` is the SHARED registry (same instance for all workers + the search tasks,
    which persist it). Single writer on the event loop → no race (spec §3).
    """

    catalog: CatalogRepository
    engine: MatchingEngine
    wake_hub: WakeHub
    backoff: "BackoffRegistry"
    telemetry: Telemetry
    wall_clock: WallClock


class SearchWorker:
    """Runs one client's search tasks; never closes the client, which composition owns."""

    def __init__(self, client_name: str, client: SearchClient, deps: WorkerDeps) -> None:
        self._client_name = client_name
        self._client_backoff_key = BackoffKey(client_name, None)
        self._client = client
        self._deps = deps
        self._connected = False

    @property
    def channels(self) -> tuple[str, ...]:
        """The channels its client declares."""
        return self._client.channels

    def seconds_until_ready(self, channel: str) -> float:
        """How long until neither the client nor ``channel`` is backed off."""
        backoff = self._deps.backoff
        return max(
            backoff.seconds_remaining(self._client_backoff_key),
            backoff.seconds_remaining(BackoffKey(self._client_name, channel)),
        )

    async def _ensure_connected(self) -> bool:
        """Connects the client if needed. Returns ``False`` if the client stays down."""
        if self._connected:
            return True
        try:
            await self._client.connect()
        except ClientUnreachableError as error:
            delay = self._deps.backoff.record_failure(self._client_backoff_key)
            _logger.warning(
                "client %s unreachable (%s): reconnect backoff %.1fs",
                self._client_name,
                error,
                delay,
            )
            await self._deps.telemetry.emit(ClientUnreachable(self._client_name))
            return False
        self._connected = True
        _logger.info("client %s connected", self._client_name)
        return True

    async def _record_observations(
        self, channel: str, observations: tuple[FileObservation, ...]
    ) -> int:
        """Per-obs pipeline; returns the number of CHANGED verdicts (logging). A
        ``RepositoryError`` per obs is ABSORBED inside ``record_observation`` (spec §7)."""
        await self._deps.telemetry.emit(
            SearchExecuted(self._client_name, channel, len(observations))
        )
        changed = 0
        for observation in observations:
            if await record_observation(
                observation,
                catalog=self._deps.catalog,
                engine=self._deps.engine,
                wake_hub=self._deps.wake_hub,
                telemetry=self._deps.telemetry,
                wall_clock=self._deps.wall_clock,
                client_name=self._client_name,
                channel=channel,
            ):
                changed += 1
        return changed

    async def run_task(self, task: SearchTask) -> None:
        """One search, run once ``seconds_until_ready`` is 0. Never raises: backs off and logs."""
        channel_backoff_key = BackoffKey(self._client_name, task.channel)
        if not await self._ensure_connected():
            return
        try:
            results = await self._client.search(task.keyword, task.channel, SEARCH_BUDGET_SECONDS)
        except SearchFailedError as error:
            delay = self._deps.backoff.record_failure(channel_backoff_key)
            _logger.warning(
                "client %s channel %s failed (%s): backoff %.1fs",
                self._client_name,
                task.channel,
                error,
                delay,
            )
            await self._deps.telemetry.emit(SearchFailed(self._client_name, task.channel))
            return
        except ClientUnreachableError as error:
            self._connected = False
            delay = self._deps.backoff.record_failure(self._client_backoff_key)
            _logger.warning(
                "client %s unreachable (%s), client down, backoff %.1fs",
                self._client_name,
                error,
                delay,
            )
            await self._deps.telemetry.emit(ClientUnreachable(self._client_name))
            return
        changed = await self._record_observations(task.channel, results)
        self._deps.backoff.reset(channel_backoff_key)
        # connect() proves nothing: it may not log in
        self._deps.backoff.reset(self._client_backoff_key)
        _logger.info(
            "client %s: '%s'/%s → %d verdict(s) changed",
            self._client_name,
            task.keyword,
            task.channel,
            changed,
        )

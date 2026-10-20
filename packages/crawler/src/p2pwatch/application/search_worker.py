"""One client's searches: a task's search, its observations recorded, and the backoff a failure
earns, per client when unreachable and per channel when refused (stage 2, D4 and D7)."""

from dataclasses import dataclass
from datetime import timedelta

from catalog_matching.domain.engine import MatchingEngine
from p2pwatch.application.record_observations import record_observation
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.observability.events import (
    ClientUnreachable,
    SearchExecuted,
    SearchFailed,
)
from p2pwatch.domain.persisted_wait import remaining_wait
from p2pwatch.domain.search.answer import SearchAnswer
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState, backoff_delay
from p2pwatch.ports.driven.catalog import (
    DecisionReader,
    DecisionWriter,
    ObservationReader,
    ObservationWriter,
)
from p2pwatch.ports.driven.client_errors import ClientUnreachableError, SearchFailedError
from p2pwatch.ports.driven.clock import MonotonicClock, WallClock
from p2pwatch.ports.driven.jitter_generator import JitterGenerator
from p2pwatch.ports.driven.logger import Logger
from p2pwatch.ports.driven.search_client import SearchClient
from p2pwatch.ports.driven.telemetry import EventEmitter
from p2pwatch.ports.driven.waker import Waker

# A ceiling, not a duration: above Kad's 45 s and an ed2k sweep, it guards a search never ending.
SEARCH_BUDGET_SECONDS = 120.0


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
    """The backoff every worker shares, each wait a persisted wait: measured on the monotonic
    clock, resumed through ``remaining_wait`` after a restart."""

    def __init__(
        self,
        policy: BackoffPolicy,
        wall_clock: WallClock,
        monotonic_clock: MonotonicClock,
        jitter_generator: JitterGenerator,
    ) -> None:
        self._policy = policy
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock
        self._jitter_generator = jitter_generator
        self._state_by_key: dict[BackoffKey, BackoffState] = {}
        self._deadline_by_key: dict[BackoffKey, MonotonicInstant] = {}

    def load_from(self, states: dict[BackoffKey, BackoffState]) -> None:
        """Resumes the waits a previous run persisted."""
        wall_now = self._wall_clock.now()
        monotonic_now = self._monotonic_clock.now()
        self._state_by_key = dict(states)
        self._deadline_by_key = {
            backoff_key: monotonic_now + remaining_wait(state.started_at, state.delay, wall_now)
            for backoff_key, state in states.items()
        }

    def snapshot(self) -> dict[BackoffKey, BackoffState]:
        """Copy of the current map, to persist."""
        return dict(self._state_by_key)

    def is_in_backoff(self, backoff_key: BackoffKey) -> bool:
        return self.time_until_retry(backoff_key) > timedelta(0)

    def time_until_retry(self, backoff_key: BackoffKey) -> timedelta:
        """What is left of ``backoff_key``'s wait, zero when it has none or it has ended."""
        deadline = self._deadline_by_key.get(backoff_key)
        if deadline is None:
            return timedelta(0)
        return max(timedelta(0), deadline - self._monotonic_clock.now())

    def record_failure(self, backoff_key: BackoffKey) -> timedelta:
        """Counts one more attempt and starts its wait, delay plus jitter. Returns the delay, for
        the log."""
        if self.is_in_backoff(backoff_key):  # a concurrent search started before it: same round
            return self.time_until_retry(backoff_key)
        attempts = (
            self._state_by_key[backoff_key].attempts + 1 if backoff_key in self._state_by_key else 1
        )
        delay_seconds = backoff_delay(
            attempts,
            base=self._policy.base_seconds,
            cap=self._policy.cap_seconds,
            factor=self._policy.factor,
        )
        delay_seconds += self._jitter_generator.jitter(self._policy.jitter_ratio * delay_seconds)
        delay = timedelta(seconds=delay_seconds)
        self._state_by_key[backoff_key] = BackoffState(attempts, self._wall_clock.now(), delay)
        self._deadline_by_key[backoff_key] = self._monotonic_clock.now() + delay
        return delay

    def reset(self, backoff_key: BackoffKey) -> None:
        """Clears the backoff of a key (success)."""
        self._state_by_key.pop(backoff_key, None)
        self._deadline_by_key.pop(backoff_key, None)


@dataclass
class WorkerDeps:
    """A worker's shared dependencies (composition assembles them once).

    ``backoff`` is the SHARED registry (same instance for all workers + the search tasks,
    which persist it). Single writer on the event loop → no race (spec §3).
    """

    observation_writer: ObservationWriter
    observation_reader: ObservationReader
    decision_writer: DecisionWriter
    decision_reader: DecisionReader
    engine: MatchingEngine
    waker: Waker
    backoff: "BackoffRegistry"
    event_emitter: EventEmitter
    wall_clock: WallClock
    logger: Logger
    observation_logger: Logger  # record_observation's


class SearchWorker:
    """Runs one client's search tasks; never closes the client, which composition owns."""

    def __init__(self, client_name: str, client: SearchClient, deps: WorkerDeps) -> None:
        self._client_name = client_name
        self._client_backoff_key = BackoffKey(client_name, None)
        self._client = client
        self._deps = deps

    @property
    def channels(self) -> tuple[str, ...]:
        """The channels its client declares."""
        return self._client.channels()

    def time_until_ready(self, channel: str) -> timedelta:
        """How long until neither the client nor ``channel`` is backed off."""
        backoff = self._deps.backoff
        return max(
            backoff.time_until_retry(self._client_backoff_key),
            backoff.time_until_retry(BackoffKey(self._client_name, channel)),
        )

    async def _record_observations(self, channel: str, answer: SearchAnswer, node_id: str) -> int:
        """Per-obs pipeline; returns the number of CHANGED verdicts (logging). A
        ``RepositoryError`` per obs is ABSORBED inside ``record_observation`` (spec §7)."""
        await self._deps.event_emitter.emit(
            SearchExecuted(
                self._client_name, channel, len(answer.reported_files), answer.skipped_result_count
            ),
            node_id,
        )
        changed = 0
        for reported_file in answer.reported_files:
            if await record_observation(
                reported_file,
                observation_writer=self._deps.observation_writer,
                observation_reader=self._deps.observation_reader,
                decision_writer=self._deps.decision_writer,
                decision_reader=self._deps.decision_reader,
                engine=self._deps.engine,
                waker=self._deps.waker,
                event_emitter=self._deps.event_emitter,
                wall_clock=self._deps.wall_clock,
                client_name=self._client_name,
                channel=channel,
                logger=self._deps.observation_logger,
                node_id=node_id,
            ):
                changed += 1
        return changed

    async def run_task(self, task: SearchTask, node_id: str) -> None:
        """One search, run once ``time_until_ready`` is zero. Never raises: backs off and logs."""
        channel_backoff_key = BackoffKey(self._client_name, task.channel)
        try:
            answer = await self._client.search(task.keyword, task.channel, SEARCH_BUDGET_SECONDS)
        except SearchFailedError as error:
            delay = self._deps.backoff.record_failure(channel_backoff_key)
            self._deps.logger.warning(
                "client %s channel %s failed (%s): backoff %.1fs",
                self._client_name,
                task.channel,
                error,
                delay.total_seconds(),
            )
            await self._deps.event_emitter.emit(
                SearchFailed(self._client_name, task.channel), node_id
            )
            return
        except ClientUnreachableError as error:
            delay = self._deps.backoff.record_failure(self._client_backoff_key)
            self._deps.logger.warning(
                "client %s unreachable (%s), client down, backoff %.1fs",
                self._client_name,
                error,
                delay.total_seconds(),
            )
            await self._deps.event_emitter.emit(ClientUnreachable(self._client_name), node_id)
            return
        changed = await self._record_observations(task.channel, answer, node_id)
        self._deps.backoff.reset(channel_backoff_key)
        self._deps.backoff.reset(self._client_backoff_key)
        self._deps.logger.info(
            "client %s: '%s'/%s → %d verdict(s) changed",
            self._client_name,
            task.keyword,
            task.channel,
            changed,
        )

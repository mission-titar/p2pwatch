"""The backoff every search worker shares, per client and per channel (stage 2, D4 and D7)."""

from dataclasses import dataclass
from datetime import timedelta

from p2pwatch.application.ports.driven.backoff_state_reader import BackoffStateReader
from p2pwatch.application.ports.driven.jitter_generator import JitterGenerator
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.persisted_wait import remaining_wait
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState, backoff_delay


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
        backoff_state_reader: BackoffStateReader,
    ) -> None:
        self._policy = policy
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock
        self._jitter_generator = jitter_generator
        self._backoff_state_reader = backoff_state_reader
        self._state_by_key: dict[BackoffKey, BackoffState] = {}
        self._deadline_by_key: dict[BackoffKey, MonotonicInstant] = {}

    def resume_waits(self) -> None:
        """Resumes the waits a previous run saved, each holding what is left of it."""
        states = self._backoff_state_reader.read_backoff_states()
        wall_now = self._wall_clock.now()
        monotonic_now = self._monotonic_clock.now()
        self._state_by_key = dict(states)
        self._deadline_by_key = {
            backoff_key: monotonic_now
            + remaining_wait(state.started_at, duration=state.delay, now=wall_now)
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

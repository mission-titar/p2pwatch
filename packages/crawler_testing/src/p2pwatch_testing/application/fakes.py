"""Deterministic fakes for the application-layer tests (spec §8).

``FakeSearchClient``: results SCRIPTED per ``search`` call, injectable failures
(``ClientUnreachableError``/``SearchFailedError``) at ``connect``/``search``.
``FakeTime``: one timeline read through a wall and a monotonic clock.
``TickingMonotonicClock``: each read a second after the previous one.
``FakeRng``: FIXED jitter (determinism). ``FakeLogger``: keeps each line it is given.
``RecordingWakeHub``: captures woken subjects. The repos are the REAL SQLite repos
(spec §8: "real repos on tmp_path"): no fakes here.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from p2pwatch.domain.observability.events import Event
from p2pwatch.domain.observation import FileObservation
from p2pwatch.ports.driven.client_errors import ClientUnreachableError, SearchFailedError
from p2pwatch.ports.driven.clock import MonotonicInstant
from p2pwatch.ports.driven.logger import Logger
from p2pwatch.ports.driven.search_client import SearchAnswer


class FakeTime:
    """One fake timeline the test drives, read through ``wall`` and ``monotonic``: ``advance``
    moves both clocks, ``step_wall`` the wall clock alone, as a clock step does."""

    def __init__(self, start: datetime | None = None) -> None:
        self._wall_now = start or datetime(2026, 6, 12, tzinfo=UTC)
        self._monotonic_now = MonotonicInstant(0)
        self.sleeps: list[timedelta] = []
        self.wall = FakeWallClock(self)
        self.monotonic = FakeMonotonicClock(self)

    def advance(self, duration: timedelta) -> None:
        self._wall_now += duration
        self._monotonic_now += duration

    def step_wall(self, step: timedelta) -> None:
        self._wall_now += step


class FakeWallClock:
    def __init__(self, fake_time: FakeTime) -> None:
        self._fake_time = fake_time

    def now(self) -> datetime:
        return self._fake_time._wall_now


class TickingWallClock(FakeWallClock):
    """Each ``now()`` a minute after the previous one: a write shows which read it took."""

    def now(self) -> datetime:
        moment = super().now()
        self._fake_time.advance(timedelta(minutes=1))
        return moment


class FakeMonotonicClock:
    """Its ``sleep`` advances the timeline at once, without a real wait."""

    def __init__(self, fake_time: FakeTime) -> None:
        self._fake_time = fake_time

    def now(self) -> MonotonicInstant:
        return self._fake_time._monotonic_now

    async def sleep(self, duration: timedelta) -> None:
        self._fake_time.sleeps.append(duration)
        self._fake_time.advance(duration)
        await asyncio.sleep(0)  # yield control without a real wait


class TickingMonotonicClock(FakeMonotonicClock):
    """Each ``now()`` a second after the previous one: a query's every check sees time pass."""

    def now(self) -> MonotonicInstant:
        moment = super().now()
        self._fake_time.advance(timedelta(seconds=1))
        return moment


class FakeRng:
    """DETERMINISTIC fake rng: constant jitter (``jitter_value``).

    ``jitter`` returns
    ``jitter_value`` (0.0 by default → backoff/pause = exact NOMINAL value), but honors
    the port CONTRACT like the real ``SeededRng``: ``span <= 0`` → ``0.0`` (otherwise the
    min==max pause test would lie about real behavior)."""

    def __init__(self, *, jitter_value: float = 0.0) -> None:
        self._jitter_value = jitter_value
        self.jitter_spans: list[float] = []

    def jitter(self, span: float) -> float:
        self.jitter_spans.append(span)
        if span <= 0:
            return 0.0
        return self._jitter_value


@dataclass(frozen=True)
class LoggedLine:
    level: Literal["info", "warning", "error"]
    message: str


class FakeLogger(Logger):
    """Keeps each line, its arguments formatted in as ``logging`` does."""

    def __init__(self) -> None:
        self.lines: list[LoggedLine] = []

    def info(self, message: str, *args: object) -> None:
        self.lines.append(LoggedLine("info", _formatted(message, args)))

    def warning(self, message: str, *args: object) -> None:
        self.lines.append(LoggedLine("warning", _formatted(message, args)))

    def error(self, message: str, *args: object) -> None:
        self.lines.append(LoggedLine("error", _formatted(message, args)))


def _formatted(message: str, args: tuple[object, ...]) -> str:
    return message % args if args else message


class RecordingTelemetry:
    """Fake telemetry: captures emitted events (the test asserts the sequence)."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    async def emit(self, event: Event) -> None:
        self.events.append(event)


class RecordingWakeHub:
    """Wake hub that RECORDS woken subjects (the test inspects/awaits)."""

    def __init__(self) -> None:
        self.woken_subjects: list[str] = []
        self._events: dict[str, asyncio.Event] = {}

    def wake(self, subject: str) -> None:
        self.woken_subjects.append(subject)
        self._events.setdefault(subject, asyncio.Event()).set()

    async def wait(self, subject: str) -> None:
        event = self._events.setdefault(subject, asyncio.Event())
        await event.wait()
        event.clear()


class FakeSearchClient:
    """Scripted client (satisfies SearchClient structurally, spec §8).

    ``results``: list of observation tuples, one per ``search`` call (exhausted → empty
    tuple). ``search_failures``: exceptions to raise on the first N ``search`` calls (then
    success). Every answer reports ``skipped_result_count`` skipped results.
    """

    channels: tuple[str, ...] = ("ed2k", "kad")

    def __init__(
        self,
        *,
        results: list[tuple[FileObservation, ...]] | None = None,
        search_failures: list[Exception] | None = None,
        skipped_result_count: int = 0,
    ) -> None:
        self._results = list(results or [])
        self._skipped_result_count = skipped_result_count
        self._search_failures = list(search_failures or [])
        self.searches: list[tuple[str, str]] = []
        self.budgets: list[float] = []

    async def search(self, keyword: str, channel: str, budget_seconds: float) -> SearchAnswer:
        self.searches.append((keyword, channel))
        self.budgets.append(budget_seconds)
        if self._search_failures:
            raise self._search_failures.pop(0)
        observations = self._results.pop(0) if self._results else ()
        return SearchAnswer(observations, self._skipped_result_count)


def make_unreachable(message: str = "down") -> ClientUnreachableError:
    return ClientUnreachableError(message)


def make_search_failed(message: str = "EC_OP_FAILED") -> SearchFailedError:
    return SearchFailedError(message)

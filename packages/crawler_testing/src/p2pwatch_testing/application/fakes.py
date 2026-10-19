"""Deterministic fakes for the application-layer tests (spec §8).

``FakeSearchClient``: results SCRIPTED per ``search`` call, injectable failures
(``ClientUnreachableError``/``SearchFailedError``) at ``connect``/``search``.
``FakeTime``: one timeline read through a wall and a monotonic clock.
``TickingMonotonicClock``: each read a second after the previous one.
``FakeRng``: FIXED jitter (determinism). ``FakeLogger``: keeps each line it is given.
``FakeNodeIdStore`` and ``FakeNodeIdGenerator``: the node id's stored and new values.
``FakeRunState``: keeps each change; ``FakeCrawlControls``: each control the webui calls.
``FakeClientStatusReader``: reads the readings it is given; ``FakeNodeStateReader``, the state.
``RecordingWakeHub``: captures woken subjects. The repos are the REAL SQLite repos
(spec §8: "real repos on tmp_path"): no fakes here.
"""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from p2pwatch.domain.node_state import NodeState
from p2pwatch.domain.observability.events import Event
from p2pwatch.domain.observation import ReportedFile
from p2pwatch.ports.driven.client_errors import ClientUnreachableError, SearchFailedError
from p2pwatch.ports.driven.client_status import ClientStatusReader, PublishedReading
from p2pwatch.ports.driven.clock import MonotonicInstant
from p2pwatch.ports.driven.logger import Logger
from p2pwatch.ports.driven.node_id import NodeIdGenerator, NodeIdReader, NodeIdWriter
from p2pwatch.ports.driven.node_state_reader import NodeStateReader
from p2pwatch.ports.driven.run_state import RunStateReader, RunStateWriter
from p2pwatch.ports.driven.search_client import SearchAnswer
from p2pwatch.ports.driving.crawl_pauser import CrawlPauser
from p2pwatch.ports.driving.crawl_resumer import CrawlResumer
from p2pwatch.ports.driving.shutdown_requester import ShutdownRequester


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


class FakeNodeIdStore(NodeIdReader, NodeIdWriter):
    """``local.db``'s node id: counts its reads, keeps each id recorded with its instant."""

    def __init__(self, *, stored_node_id: str | None) -> None:
        self._stored_node_id = stored_node_id
        self.reads = 0
        self.recorded: list[tuple[str, datetime]] = []

    def read_node_id(self) -> str | None:
        self.reads += 1
        return self._stored_node_id

    def record_node_id(self, node_id: str, created_at: datetime) -> None:
        self.recorded.append((node_id, created_at))
        self._stored_node_id = node_id


class FakeNodeIdGenerator(NodeIdGenerator):
    """Draws the one id it is given."""

    def __init__(self, node_id: str) -> None:
        self._node_id = node_id

    def new_node_id(self) -> str:
        return self._node_id


class FakeRunState(RunStateWriter, RunStateReader):
    """Keeps each change by its method's name; reads ``paused``, which no change moves."""

    def __init__(self, *, paused: bool = False) -> None:
        self.changes: list[str] = []
        self.paused = paused

    def pause(self) -> None:
        self.changes.append("pause")

    def resume(self) -> None:
        self.changes.append("resume")

    def request_shutdown(self) -> None:
        self.changes.append("request_shutdown")

    def is_paused(self) -> bool:
        return self.paused


class FakeCrawlControls(CrawlPauser, CrawlResumer, ShutdownRequester):
    """The three control use cases: keeps each call by its operation's name."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def pause_crawl(self) -> None:
        self.calls.append("pause_crawl")

    def resume_crawl(self) -> None:
        self.calls.append("resume_crawl")

    def request_shutdown(self) -> None:
        self.calls.append("request_shutdown")


class FakeClientStatusReader(ClientStatusReader):
    """Reads the readings it is given."""

    def __init__(self, published_readings: Mapping[str, PublishedReading | None]) -> None:
        self._published_readings = published_readings

    def read_readings(self) -> Mapping[str, PublishedReading | None]:
        return self._published_readings


class FakeNodeStateReader(NodeStateReader):
    """Reads the state it is given."""

    def __init__(self, node_state: NodeState) -> None:
        self._node_state = node_state

    def read_node_state(self) -> NodeState:
        return self._node_state


class RecordingTelemetry:
    """Fake telemetry: captures emitted events (the test asserts the sequence)."""

    def __init__(self) -> None:
        self.events: list[Event] = []
        self.node_ids: set[str] = set()  # every call's

    async def emit(self, event: Event, node_id: str) -> None:
        self.events.append(event)
        self.node_ids.add(node_id)


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

    ``results``: list of reported file tuples, one per ``search`` call (exhausted → empty
    tuple). ``search_failures``: exceptions to raise on the first N ``search`` calls (then
    success). Every answer reports ``skipped_result_count`` skipped results.
    """

    channels: tuple[str, ...] = ("ed2k", "kad")

    def __init__(
        self,
        *,
        results: list[tuple[ReportedFile, ...]] | None = None,
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
        reported_files = self._results.pop(0) if self._results else ()
        return SearchAnswer(reported_files, self._skipped_result_count)


def make_unreachable(message: str = "down") -> ClientUnreachableError:
    return ClientUnreachableError(message)


def make_search_failed(message: str = "EC_OP_FAILED") -> SearchFailedError:
    return SearchFailedError(message)

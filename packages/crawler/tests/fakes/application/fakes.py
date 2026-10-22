"""Deterministic fakes for the application-layer tests (spec §8).

``FakeSearchClient``: results SCRIPTED per ``search`` call, injectable failures
(``ClientUnreachableError``/``SearchFailedError``) at ``search``.
``FakeTime``: one timeline read through a wall and a monotonic clock.
``TickingMonotonicClock``: each read a second after the previous one.
``FakeJitterGenerator``: FIXED jitter (determinism). ``FakeLogger``: keeps each line it is given.
``FakeNodeIdStore`` and ``FakeNodeIdGenerator``: the node id's stored and new values.
``FakeRunState``: keeps each change; ``FakeCrawlPauser``, ``FakeCrawlResumer`` and
``FakeShutdownRequester``: each control the webui calls.
``FakeClientStatusReader``: reads the readings it is given; ``FakeNodeStateReader``, the state.
``FakeCrawlSummarizer`` and ``FakeNodeDescriber``: the dashboard's and the node page's use cases.
``FakeWaker``: captures woken subjects. The repos are the REAL SQLite repos
(spec §8: "real repos on tmp_path"): no fakes here.
"""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from p2pwatch.domain.catalog_entry import CatalogEntrySort, SortDirection
from p2pwatch.domain.console_query import ConsoleDatabase
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.node_state import NodeState
from p2pwatch.domain.observability.events import Event
from p2pwatch.domain.observation import ReportedFile
from p2pwatch.domain.search.answer import SearchAnswer
from p2pwatch.domain.status_reading import PublishedReading
from p2pwatch.ports.driven.client_errors import ClientUnreachableError, SearchFailedError
from p2pwatch.ports.driven.client_status import ClientStatusReader
from p2pwatch.ports.driven.clock import MonotonicClock, WallClock
from p2pwatch.ports.driven.jitter_generator import JitterGenerator
from p2pwatch.ports.driven.logger import Logger
from p2pwatch.ports.driven.node_id import NodeIdGenerator, NodeIdReader, NodeIdWriter
from p2pwatch.ports.driven.node_state_reader import NodeStateReader
from p2pwatch.ports.driven.run_state import RunStateReader, RunStateWriter
from p2pwatch.ports.driven.search_client import SearchClient
from p2pwatch.ports.driven.telemetry import EventEmitter
from p2pwatch.ports.driven.waker import Waker
from p2pwatch.ports.driving.console_query_runner import ConsoleQueryOutcome, ConsoleQueryRunner
from p2pwatch.ports.driving.crawl_pauser import CrawlPauser
from p2pwatch.ports.driving.crawl_resumer import CrawlResumer
from p2pwatch.ports.driving.crawl_summarizer import CrawlSummarizer, CrawlSummary
from p2pwatch.ports.driving.file_describer import FileDescriber, FileDescription
from p2pwatch.ports.driving.file_lister import FileLister, FileListing
from p2pwatch.ports.driving.node_describer import NodeDescriber, NodeDescription
from p2pwatch.ports.driving.shutdown_requester import ShutdownRequester
from p2pwatch.ports.driving.source_describer import SourceDescriber, SourceDescription
from p2pwatch.ports.driving.source_lister import SourceLister, SourceListing
from p2pwatch.ports.driving.source_name_describer import SourceNameDescriber, SourceNameDescription


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


class FakeWallClock(WallClock):
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


class FakeMonotonicClock(MonotonicClock):
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


class FakeJitterGenerator(JitterGenerator):
    """DETERMINISTIC jitter: ``jitter`` returns ``jitter_value`` (0.0 by default → backoff/pause =
    exact NOMINAL value), but honors the port CONTRACT like the real ``RandomJitterGenerator``:
    ``span <= 0`` → ``0.0`` (otherwise the min==max pause test would lie about real behavior)."""

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

    def shut_down(self) -> None:
        self.changes.append("shut_down")

    def is_paused(self) -> bool:
        return self.paused


class FakeCrawlPauser(CrawlPauser):
    """Keeps each call by its operation's name."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def pause_crawl(self) -> None:
        self.calls.append("pause_crawl")


class FakeCrawlResumer(CrawlResumer):
    """Keeps each call by its operation's name."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def resume_crawl(self) -> None:
        self.calls.append("resume_crawl")


class FakeShutdownRequester(ShutdownRequester):
    """Keeps each call by its operation's name."""

    def __init__(self) -> None:
        self.calls: list[str] = []

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


class FakeCrawlSummarizer(CrawlSummarizer):
    """Summarizes the crawl as it is given."""

    def __init__(self, crawl_summary: CrawlSummary) -> None:
        self._crawl_summary = crawl_summary

    def summarize_crawl(self) -> CrawlSummary:
        return self._crawl_summary


@dataclass(frozen=True)
class ListFilesCall:
    """The arguments of one ``list_files`` call."""

    target_id: str | None
    tier: str | None
    search_text: str | None
    matched_only: bool
    sort: CatalogEntrySort
    direction: SortDirection
    page: int


class FakeFileLister(FileLister):
    """Lists the files it is given, and keeps each call's arguments."""

    def __init__(self, file_listing: FileListing) -> None:
        self._file_listing = file_listing
        self.calls: list[ListFilesCall] = []

    def list_files(
        self,
        *,
        target_id: str | None,
        tier: str | None,
        search_text: str | None,
        matched_only: bool,
        sort: CatalogEntrySort,
        direction: SortDirection,
        page: int,
    ) -> FileListing:
        call = ListFilesCall(target_id, tier, search_text, matched_only, sort, direction, page)
        self.calls.append(call)
        return self._file_listing


@dataclass(frozen=True)
class DescribeFileCall:
    """The arguments of one ``describe_file`` call."""

    file_id: bytes
    requested_since: datetime | None
    requested_until: datetime | None


class FakeFileDescriber(FileDescriber):
    """Describes any file as it is given, and keeps each call's arguments."""

    def __init__(self, file_description: FileDescription | None) -> None:
        self._file_description = file_description
        self.calls: list[DescribeFileCall] = []

    def describe_file(
        self,
        file_id: bytes,
        *,
        requested_since: datetime | None,
        requested_until: datetime | None,
    ) -> FileDescription | None:
        self.calls.append(DescribeFileCall(file_id, requested_since, requested_until))
        return self._file_description


@dataclass(frozen=True)
class ListSourcesCall:
    """The arguments of one ``list_sources`` call."""

    search_text: str | None
    page: int


class FakeSourceLister(SourceLister):
    """Lists the sources it is given, and keeps each call's arguments."""

    def __init__(self, source_listing: SourceListing) -> None:
        self._source_listing = source_listing
        self.calls: list[ListSourcesCall] = []

    def list_sources(self, *, search_text: str | None, page: int) -> SourceListing:
        self.calls.append(ListSourcesCall(search_text, page))
        return self._source_listing


@dataclass(frozen=True)
class DescribeSourceCall:
    """The arguments of one ``describe_source`` call."""

    source_id: bytes
    page: int
    requested_since: datetime | None
    requested_until: datetime | None


class FakeSourceDescriber(SourceDescriber):
    """Describes any source as it is given, and keeps each call's arguments."""

    def __init__(self, source_description: SourceDescription | None) -> None:
        self._source_description = source_description
        self.calls: list[DescribeSourceCall] = []

    def describe_source(
        self,
        source_id: bytes,
        *,
        page: int,
        requested_since: datetime | None,
        requested_until: datetime | None,
    ) -> SourceDescription | None:
        self.calls.append(DescribeSourceCall(source_id, page, requested_since, requested_until))
        return self._source_description


@dataclass(frozen=True)
class DescribeSourceNameCall:
    """The arguments of one ``describe_source_name`` call."""

    source_name: str
    page: int
    requested_since: datetime | None
    requested_until: datetime | None


class FakeSourceNameDescriber(SourceNameDescriber):
    """Describes any source name as it is given, and keeps each call's arguments."""

    def __init__(self, source_name_description: SourceNameDescription | None) -> None:
        self._source_name_description = source_name_description
        self.calls: list[DescribeSourceNameCall] = []

    def describe_source_name(
        self,
        source_name: str,
        *,
        page: int,
        requested_since: datetime | None,
        requested_until: datetime | None,
    ) -> SourceNameDescription | None:
        call = DescribeSourceNameCall(source_name, page, requested_since, requested_until)
        self.calls.append(call)
        return self._source_name_description


class FakeNodeDescriber(NodeDescriber):
    """Describes the node as it is given."""

    def __init__(self, node_description: NodeDescription) -> None:
        self._node_description = node_description

    def describe_node(self) -> NodeDescription:
        return self._node_description


@dataclass(frozen=True)
class RunConsoleQueryCall:
    """The arguments of one ``run_console_query`` call."""

    database: ConsoleDatabase
    sql: str


class FakeConsoleQueryRunner(ConsoleQueryRunner):
    """Answers any query with the outcome it is given, and keeps each call's arguments."""

    def __init__(self, console_query_outcome: ConsoleQueryOutcome) -> None:
        self._console_query_outcome = console_query_outcome
        self.calls: list[RunConsoleQueryCall] = []

    def run_console_query(self, database: ConsoleDatabase, sql: str) -> ConsoleQueryOutcome:
        self.calls.append(RunConsoleQueryCall(database, sql))
        return self._console_query_outcome


class FakeEventEmitter(EventEmitter):
    """Captures emitted events (the test asserts the sequence)."""

    def __init__(self) -> None:
        self.events: list[Event] = []
        self.node_ids: set[str] = set()  # every call's

    async def emit(self, event: Event, node_id: str) -> None:
        self.events.append(event)
        self.node_ids.add(node_id)


class FakeWaker(Waker):
    """Waker that RECORDS woken subjects (the test inspects/awaits)."""

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


class FakeSearchClient(SearchClient):
    """Scripted client (spec §8): ``channels`` are the ones it declares.

    ``results``: list of reported file tuples, one per ``search`` call (exhausted → empty
    tuple). ``search_failures``: exceptions to raise on the first N ``search`` calls (then
    success). Every answer reports ``skipped_result_count`` skipped results.
    """

    def __init__(
        self,
        *,
        channels: tuple[str, ...] = ("ed2k", "kad"),
        results: list[tuple[ReportedFile, ...]] | None = None,
        search_failures: list[Exception] | None = None,
        skipped_result_count: int = 0,
    ) -> None:
        self._channels = channels
        self._results = list(results or [])
        self._skipped_result_count = skipped_result_count
        self._search_failures = list(search_failures or [])
        self.searches: list[tuple[str, str]] = []
        self.budgets: list[float] = []

    def channels(self) -> tuple[str, ...]:
        return self._channels

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

"""The works over the node's aMule client as the node builds them, at its start and over each
client built anew: their turns sent to that client, their checks recorded on the parts built
once."""

import sqlite3
from collections.abc import Iterator
from contextlib import suppress
from datetime import timedelta
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.amule_api.amule_api_client import AmuleApiClient
from p2pwatch.adapters.driven.config.crawler_config import read_matcher_config, read_targets
from p2pwatch.adapters.driven.in_memory_status_reading_store import InMemoryStatusReadingStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.application.steps.backoff_registry import BackoffPolicy, BackoffRegistry
from p2pwatch.application.steps.backoff_saver import BackoffSaver
from p2pwatch.application.steps.cataloguer import Cataloguer
from p2pwatch.application.steps.file_judge import FileJudge
from p2pwatch.application.steps.work import SupervisedWork
from p2pwatch.composition.amule_client_works import AmuleClientWorks, DownloadSteps
from p2pwatch.composition.work_time_limits import AmuleWorkTimeLimits
from p2pwatch.domain.crawler_config import DownloadConfig
from p2pwatch.domain.crawler_function import CrawlerFunction
from p2pwatch.domain.expected_error import ExpectedError
from p2pwatch.domain.health.health_rule import HealthRule
from p2pwatch.domain.identifiers import ClientName, Keyword, NodeId
from p2pwatch.domain.matching.engine import MatchingEngine
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.observability.notification import RelayedLogLine
from p2pwatch.domain.status_reading import CHANNEL_NOT_CONNECTED, SEARCHES_FAILED
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore
from tests.fakes.adapters.driven.fake_jitter_generator import FakeJitterGenerator
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_search_start_store import FakeSearchStartStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.fakes.fake_amule_api import FakeAmuleApi, error
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    open_catalog,
    open_local,
)
from tests.support.application.steps.node_health import build_node_health
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes

pytestmark = pytest.mark.asyncio

_AMULED = ClientName("amuled")
_NODE_ID = NodeId("n1")
_MATCHER = Path(__file__).resolve().parents[4] / "deploy" / "matcher.yml"
_TARGETS = Path(__file__).resolve().parents[1] / "fixtures" / "golden_targets.yaml"
_KEYWORDS = ["keroro", "titar"]
_TRACKING = ["download tracking amuled", "source tracking amuled"]
_SEARCHES = [
    "search 'keroro' amuled ed2k",
    "search 'titar' amuled ed2k",
    "search 'keroro' amuled kad",
    "search 'titar' amuled kad",
]
# A floor no disk reaches: each reading of the free space is under it.
_FLOOR_NO_DISK_REACHES = 2**62
_START = MonotonicInstant(nanoseconds=0)  # where ``FakeTime``'s monotonic clock starts
_LOGIN = ("POST", "/api/v1/auth/login")
_CONNECTED = {"state": "connected", "high_id": True, "firewalled_tcp": False}


@pytest.fixture
def catalog_connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_catalog(tmp_path / "catalog.db")
    yield connection
    connection.close()


@pytest.fixture
def local_connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_local(tmp_path / "local.db")
    yield connection
    connection.close()


class _Node:
    """The parts a node builds once, and the log of every change of health its works record."""

    def __init__(
        self,
        *,
        tmp_path: Path,
        catalog_connection: sqlite3.Connection,
        local_connection: sqlite3.Connection,
    ) -> None:
        self.time = FakeTime()
        self.observability = ObservabilityOverFakes()
        self.health_logger = FakeLogger()
        self.node_health = build_node_health(
            observability_dispatcher=self.observability.dispatcher, logger=self.health_logger
        )
        self.observation_store = SqliteObservationStore(catalog_connection)
        self.decision_store = SqliteDecisionStore(catalog_connection)
        self.backoff_state_store = FakeBackoffStateStore()
        self.backoff = BackoffRegistry(
            BackoffPolicy(base_seconds=60.0, cap_seconds=600.0, factor=2.0, jitter_ratio=0.0),
            wall_clock=self.time.wall,
            monotonic_clock=self.time.monotonic,
            jitter_generator=FakeJitterGenerator(),
            backoff_state_reader=self.backoff_state_store,
        )
        self.tmp_path = tmp_path
        self.catalog_connection = catalog_connection
        self.local_connection = local_connection

    def client_works(self, *, downloading: bool) -> AmuleClientWorks:
        """The works over the client as the composition builds them, downloading or not."""
        return AmuleClientWorks(
            client_name=_AMULED,
            channels=self.client(FakeAmuleApi()).channels(),
            keywords=_KEYWORDS,
            download_steps=self._download_steps() if downloading else None,
            backoff=self.backoff,
            backoff_saver=BackoffSaver(
                backoff=self.backoff,
                backoff_state_writer=self.backoff_state_store,
                logger=FakeLogger(),
            ),
            cataloguer=self._cataloguer(),
            status_reading_writer=InMemoryStatusReadingStore((_AMULED,)),
            node_health=self.node_health,
            observability_dispatcher=self.observability.dispatcher,
            wall_clock=self.time.wall,
            monotonic_clock=self.time.monotonic,
            time_limits=AmuleWorkTimeLimits(
                request_bound=timedelta(seconds=60),
                search_budget=timedelta(seconds=120),
                keywords=[Keyword(keyword) for keyword in _KEYWORDS],
            ),
            node_id=_NODE_ID,
        )

    def client(self, api: FakeAmuleApi) -> AmuleApiClient:
        """A client of the node's aMule, its requests answered by ``api``."""
        search_start_store = FakeSearchStartStore()
        return AmuleApiClient(
            "amuled.test",
            client_name=_AMULED,
            port=4711,
            password=api.password,
            timeout_seconds=10.0,
            request_bound_seconds=60.0,
            page_size=500,
            progress_poll_interval=timedelta(seconds=5),
            transport_factory=api.transport,
            monotonic_clock=api.monotonic_clock,
            wall_clock=self.time.wall,
            search_start_writer=search_start_store,
            search_start_reader=search_start_store,
        )

    def _download_steps(self) -> DownloadSteps:
        return DownloadSteps(
            DownloadConfig(
                poll_interval_seconds=30.0,
                min_free_bytes=_FLOOR_NO_DISK_REACHES,
                lost_after=timedelta(days=1),
                output_directory=str(self.tmp_path),
                reappeared_after=timedelta(hours=12),
                sources_interval=timedelta(minutes=5),
            ),
            client_name=_AMULED,
            targets=read_targets(_TARGETS),
            local_connection=self.local_connection,
            catalog_connection=self.catalog_connection,
            observation_store=self.observation_store,
            decision_store=self.decision_store,
            waker=FakeWaker(),
            wall_clock=self.time.wall,
            monotonic_clock=self.time.monotonic,
            observability_dispatcher=self.observability.dispatcher,
            node_health=self.node_health,
            node_id=_NODE_ID,
        )

    def _cataloguer(self) -> Cataloguer:
        return Cataloguer(
            observation_writer=self.observation_store,
            file_judge=FileJudge(
                observation_reader=self.observation_store,
                decision_writer=self.decision_store,
                decision_reader=self.decision_store,
                engine=MatchingEngine(
                    read_matcher_config(_MATCHER),
                    targets=read_targets(_TARGETS),
                    max_filename_length=4096,
                ),
                waker=FakeWaker(),
                observability_dispatcher=self.observability.dispatcher,
                wall_clock=self.time.wall,
                node_id=_NODE_ID,
            ),
            observability_dispatcher=self.observability.dispatcher,
            wall_clock=self.time.wall,
            node_id=_NODE_ID,
            logger=FakeLogger(),
        )

    def alerts(self) -> list[str]:
        """The first line of each alert its works sent."""
        notifications = [notification for _, notification in self.observability.notifications]
        return [alert.message for alert in notifications if isinstance(alert, RelayedLogLine)]

    async def alerts_minute_by_minute(
        self, works: list[SupervisedWork], *, minutes: int
    ) -> list[tuple[int, str]]:
        """Each alert's minute since the start and first line, over a turn of every work at each
        of ``minutes``, an expected error suppressed."""
        alerts: list[tuple[int, str]] = []
        for _ in range(minutes):
            minute = (self.time.monotonic.now() - _START) // timedelta(minutes=1)
            sent = len(self.alerts())
            for supervised in works:
                with suppress(ExpectedError):
                    await supervised.work.run_once()
            alerts += [(minute, alert) for alert in self.alerts()[sent:]]
            self.time.advance(timedelta(minutes=1))
        return alerts

    def parts_changed_under(self, rule: HealthRule) -> list[str]:
        """The part of each change of health its works recorded under ``rule``, as the log names
        it: "channel amuled kad"."""
        changes = [line.message for line in self.health_logger.lines]
        return [change.split(", ")[0] for change in changes if f", {rule.name}: " in change]


@pytest.fixture
def node(
    *, tmp_path: Path, catalog_connection: sqlite3.Connection, local_connection: sqlite3.Connection
) -> _Node:
    return _Node(
        tmp_path=tmp_path, catalog_connection=catalog_connection, local_connection=local_connection
    )


def _named(works: list[SupervisedWork], *, name: str) -> SupervisedWork:
    [work] = [supervised for supervised in works if str(supervised.work) == name]
    return work


async def test_the_works_over_a_client_built_anew_send_their_requests_to_it_alone(
    node: _Node,
) -> None:
    first, built_anew = FakeAmuleApi(), FakeAmuleApi()
    client_works = node.client_works(downloading=True)
    client_works.over(node.client(first))

    asked_the_client_built_anew: list[tuple[str, bool]] = []
    for supervised in client_works.over(node.client(built_anew)):
        requests_before = len(built_anew.requests)
        await supervised.work.run_once()
        asked = len(built_anew.requests) > requests_before
        asked_the_client_built_anew.append((str(supervised.work), asked))

    assert first.requests == []
    assert asked_the_client_built_anew == [
        ("status reading amuled", True),
        ("download tracking amuled", True),
        ("source tracking amuled", True),
        ("search 'keroro' amuled ed2k", True),
        ("search 'titar' amuled ed2k", True),
        ("search 'keroro' amuled kad", True),
        ("search 'titar' amuled kad", True),
        ("stall watch amuled", False),
    ]


async def test_each_work_over_the_client_serves_its_function_the_status_reading_none(
    node: _Node,
) -> None:
    works = node.client_works(downloading=True).over(node.client(FakeAmuleApi()))

    assert [(str(supervised.work), supervised.function) for supervised in works] == [
        ("status reading amuled", None),
        *[(tracking, CrawlerFunction.DOWNLOADS) for tracking in _TRACKING],
        *[(search, CrawlerFunction.CRAWL) for search in _SEARCHES],
        ("stall watch amuled", None),
    ]


@pytest.mark.parametrize("downloading", [True, False], ids=["downloading", "not-downloading"])
async def test_the_works_over_a_client_built_anew_record_on_the_parts_built_once(
    node: _Node, *, downloading: bool
) -> None:
    client_works = node.client_works(downloading=downloading)

    first = client_works.over(node.client(FakeAmuleApi()))
    built_anew = client_works.over(node.client(FakeAmuleApi()))
    # aMule's status by default: neither channel connected, 6 readings to turn failing.
    for works in (first, built_anew):
        for _ in range(3):
            await _named(works, name="status reading amuled").work.run_once()

    tracking = _TRACKING if downloading else []
    assert [str(supervised.work) for supervised in built_anew] == [
        "status reading amuled",
        *tracking,
        *_SEARCHES,
        "stall watch amuled",
    ]
    # Three readings over each client: failing only on one part per channel, built once.
    assert node.parts_changed_under(CHANNEL_NOT_CONNECTED) == [
        "channel amuled ed2k",
        "channel amuled kad",
    ]


async def test_the_status_reading_records_a_channel_on_the_part_its_searches_record_on(
    node: _Node,
) -> None:
    works = node.client_works(downloading=False).over(node.client(FakeAmuleApi()))

    # Three searches on Kad that ran, then aMule's status by default: neither channel connected.
    for keyword in ["keroro", "titar", "keroro"]:
        await _named(works, name=f"search '{keyword}' amuled kad").work.run_once()
    for _ in range(6):
        await _named(works, name="status reading amuled").work.run_once()

    assert node.parts_changed_under(SEARCHES_FAILED) == ["channel amuled kad"]
    assert "channel amuled kad" in node.parts_changed_under(CHANNEL_NOT_CONNECTED)


async def test_a_client_built_anew_during_a_stall_keeps_it_open_until_a_search_completes(
    node: _Node,
) -> None:
    client_works = node.client_works(downloading=False)
    first = client_works.over(node.client(FakeAmuleApi()))
    await _named(first, name="stall watch amuled").work.run_once()
    node.time.advance(timedelta(minutes=15))
    await _named(first, name="stall watch amuled").work.run_once()

    built_anew = client_works.over(node.client(FakeAmuleApi()))
    await _named(built_anew, name="stall watch amuled").work.run_once()
    await _named(built_anew, name="search 'keroro' amuled kad").work.run_once()
    await _named(built_anew, name="stall watch amuled").work.run_once()

    assert node.alerts() == [
        "search stalled on amuled ed2k for 15 min",
        "search stalled on amuled kad for 15 min",
        "search on amuled kad moving again",
    ]


async def test_kad_without_contact_alerts_off_its_network_its_searches_answered_empty_stalling_not(
    node: _Node,
) -> None:
    # amuled accepts a Kad search while Kad has no contact, and ends it empty.
    api = FakeAmuleApi(
        status={"ec_connected": True, "ed2k": _CONNECTED, "kad": {"state": "connecting"}}
    )
    works = node.client_works(downloading=False).over(node.client(api))

    assert await node.alerts_minute_by_minute(works, minutes=20) == [
        (5, "amuled kad: off its network for 5 min")
    ]


async def test_amuled_unreachable_alerts_at_2_min_and_stalls_each_channel_at_15_until_it_answers(
    node: _Node,
) -> None:
    api = FakeAmuleApi(status={"ec_connected": True, "ed2k": _CONNECTED, "kad": _CONNECTED})
    api.overrides[_LOGIN] = lambda _request: error(503, code="daemon_unreachable")
    works = node.client_works(downloading=False).over(node.client(api))

    unreachable = await node.alerts_minute_by_minute(works, minutes=16)
    del api.overrides[_LOGIN]
    answering = await node.alerts_minute_by_minute(works, minutes=10)

    assert unreachable == [
        (2, "amuled unreachable for 2 min"),
        (15, "search stalled on amuled ed2k for 15 min"),
        (15, "search stalled on amuled kad for 15 min"),
    ]
    # Healthy again under 2 unanswered readings among the last 10: the ninth answered.
    assert answering == [
        (16, "search on amuled ed2k moving again"),
        (16, "search on amuled kad moving again"),
        (24, "amuled reachable again"),
    ]

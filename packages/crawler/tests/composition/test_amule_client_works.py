"""The works over the node's aMule client as the node builds them, at its start and over each
client built anew: their turns sent to that client, recorded on the parts built once."""

import asyncio
import contextlib
import sqlite3
from collections.abc import Iterator, Sequence
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
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.supervisor import Supervisor
from p2pwatch.application.steps.work import SupervisedWork
from p2pwatch.composition.amule_client_works import AmuleClientWorks, DownloadSteps
from p2pwatch.composition.node_restart_policy import node_restart_policy
from p2pwatch.composition.work_time_limits import AmuleWorkTimeLimits
from p2pwatch.domain.crawler_config import DownloadConfig
from p2pwatch.domain.download.disk_space import CONNECTED_TO_NO_NETWORK, DISK_SPACE_LOW
from p2pwatch.domain.health.external_dependency import ExternalDependency, HealthTransition
from p2pwatch.domain.health.health_rule import HealthRule, HealthState
from p2pwatch.domain.identifiers import Channel, ClientName, Keyword, NodeId
from p2pwatch.domain.matching.engine import MatchingEngine
from p2pwatch.domain.status_reading import CHANNEL_NOT_CONNECTED
from p2pwatch.domain.work_dependencies import BUGS
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore
from tests.fakes.adapters.driven.fake_jitter_generator import FakeJitterGenerator
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.fakes.adapters.driven.fake_search_start_store import FakeSearchStartStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.fakes.composition.fake_restartable import FakeRestartable
from tests.fakes.fake_amule_api import FakeAmuleApi
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    open_catalog,
    open_local,
)
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
    """The parts a node builds once, and every change of health its works record."""

    def __init__(
        self,
        *,
        tmp_path: Path,
        catalog_connection: sqlite3.Connection,
        local_connection: sqlite3.Connection,
    ) -> None:
        self.time = FakeTime()
        self.transitions: list[HealthTransition] = []
        self.node_health = NodeHealth(logger=FakeLogger(), subscribers=(self._keep,))
        self.observability = ObservabilityOverFakes()
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

    async def _keep(self, transition: HealthTransition) -> None:
        self.transitions.append(transition)

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

    def changes_under(self, rule: HealthRule) -> list[HealthTransition]:
        """Every change of health its works recorded under ``rule``."""
        return [transition for transition in self.transitions if transition.rule is rule]


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
    ]


@pytest.mark.parametrize("downloading", [True, False], ids=["downloading", "not-downloading"])
async def test_the_works_over_a_client_built_anew_are_recorded_on_the_parts_built_once(
    node: _Node, *, downloading: bool
) -> None:
    client_works = node.client_works(downloading=downloading)

    first = client_works.over(node.client(FakeAmuleApi()))
    built_anew = client_works.over(node.client(FakeAmuleApi()))

    tracking = _TRACKING if downloading else []
    assert [str(supervised.work) for supervised in built_anew] == [
        "status reading amuled",
        *tracking,
        *_SEARCHES,
    ]
    # A part keeps its own health, and compares equal to itself alone.
    assert [supervised.dependencies for supervised in built_anew] == [
        supervised.dependencies for supervised in first
    ]


async def test_the_status_reading_records_no_network_on_the_part_of_download_tracking(
    node: _Node,
) -> None:
    works = node.client_works(downloading=True).over(node.client(FakeAmuleApi()))
    status_reading = _named(works, name="status reading amuled")
    download_tracking = _named(works, name="download tracking amuled")

    # aMule's status by default: neither channel connected, 6 readings to turn failing.
    for _ in range(6):
        await status_reading.work.run_once()

    [no_network] = node.changes_under(CONNECTED_TO_NO_NETWORK)
    assert no_network.dependency is download_tracking.dependencies[0]


async def test_the_status_reading_records_a_channel_on_the_part_of_its_searches(
    node: _Node,
) -> None:
    works = node.client_works(downloading=False).over(node.client(FakeAmuleApi()))
    status_reading = _named(works, name="status reading amuled")
    kad_search = _named(works, name="search 'keroro' amuled kad")

    # aMule's status by default: neither channel connected, 6 readings to turn failing.
    for _ in range(6):
        await status_reading.work.run_once()

    [kad_not_connected] = [
        transition
        for transition in node.changes_under(CHANNEL_NOT_CONNECTED)
        if transition.dependency.channel == Channel("kad")
    ]
    assert kad_not_connected.dependency is kad_search.dependencies[1]


async def test_download_tracking_records_the_disk_on_the_part_its_turns_are_recorded_on(
    node: _Node,
) -> None:
    works = node.client_works(downloading=True).over(node.client(FakeAmuleApi()))
    download_tracking = _named(works, name="download tracking amuled")

    await download_tracking.work.run_once()

    [disk_low] = node.changes_under(DISK_SPACE_LOW)
    assert disk_low.dependency is download_tracking.dependencies[0]


async def _rebuilt(amule_client: FakeRestartable) -> None:
    while not amule_client.rebuilt_at:
        await asyncio.sleep(0)  # noqa: TID251


async def _rebuilds_once_failing(
    part: ExternalDependency, *, works: Sequence[SupervisedWork], node: _Node
) -> int:
    """How many times the client is rebuilt once the bugs rule of ``part`` turns failing, its
    restart policy and the supervisor wired as the node wires them."""
    amule_client = FakeRestartable("client amuled")
    run_state = FakeRunStateStore()
    supervisor = Supervisor(
        run_state_reader=run_state,
        monotonic_clock=node.time.monotonic,
        node_health=node.node_health,
        logger=FakeLogger(),
    )
    policy = node_restart_policy({amule_client: works}, supervisor=supervisor)
    supervision = asyncio.create_task(supervisor.supervise((), arm_shutdown_bound=lambda: None))

    await policy(
        HealthTransition(
            dependency=part, rule=BUGS, previous=HealthState.UNKNOWN, current=HealthState.FAILING
        )
    )
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(_rebuilt(amule_client), timeout=1.0)

    run_state.set_shutdown_requested()
    await supervision
    return len(amule_client.rebuilt_at)


@pytest.mark.parametrize("downloading", [True, False], ids=["downloading", "not-downloading"])
async def test_bugs_on_any_part_a_work_is_recorded_on_have_the_supervisor_rebuild_the_client(
    node: _Node, *, downloading: bool
) -> None:
    works = node.client_works(downloading=downloading).over(node.client(FakeAmuleApi()))
    parts = dict.fromkeys(part for supervised in works for part in supervised.dependencies)

    rebuilds = {
        part.name: await _rebuilds_once_failing(part, works=works, node=node) for part in parts
    }

    tracking = _TRACKING if downloading else []
    assert rebuilds == {
        name: 1
        for name in [
            "status reading amuled",
            *tracking,
            "search 'keroro' amuled ed2k",
            "channel amuled ed2k",
            "search 'titar' amuled ed2k",
            "search 'keroro' amuled kad",
            "channel amuled kad",
            "search 'titar' amuled kad",
        ]
    }

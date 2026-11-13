"""The works' factories and the mapping of components to owners, as the node wires them (spec v5
lot 4, D5): every work's feeds owned, each owner's components those its works feed, a rebuilt
client's works on the new client, a rebuilt notifier's services those its components name."""

import sqlite3
from collections.abc import Iterator
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
from p2pwatch.application.steps.health_recorder import HealthRecorder
from p2pwatch.application.steps.supervisor import SupervisedWork
from p2pwatch.composition.crawler_composition import (
    AmuleWorks,
    WebuiWorks,
    apprise_notifier,
    component_owners,
    download_steps,
)
from p2pwatch.composition.parts_built_later import PartsBuiltLater
from p2pwatch.composition.turn_time_limits import AmuleTurnTimeLimits
from p2pwatch.domain.crawler_config import DownloadConfig, NotificationTarget
from p2pwatch.domain.health.component import Component
from p2pwatch.domain.identifiers import ClientName, Keyword, NodeId
from p2pwatch.domain.matching.engine import MatchingEngine
from p2pwatch.domain.observability.notifier_outcomes import notifier_components
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.status_reading import channel_component, client_component
from p2pwatch.domain.work_components import (
    download_tracking_component,
    keyword_search_component,
    source_tracking_component,
    status_sensor_component,
    webui_component,
)
from tests.fakes.adapters.driven.fake_apprise import FakeApprise
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore
from tests.fakes.adapters.driven.fake_jitter_generator import FakeJitterGenerator
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_search_start_store import FakeSearchStartStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.fakes.composition.fake_state_owner import FakeStateOwner
from tests.fakes.fake_amule_api import FakeAmuleApi
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    open_catalog,
    open_local,
)
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes

pytestmark = pytest.mark.asyncio

_AMULED = ClientName("amuled")
_KEYWORDS = (Keyword("keroro"), Keyword("titar"))
_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


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


def _client(api: FakeAmuleApi) -> AmuleApiClient:
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
        wall_clock=FakeTime().wall,
        search_start_writer=search_start_store,
        search_start_reader=search_start_store,
    )


def _amule_works(
    *,
    tmp_path: Path,
    catalog_connection: sqlite3.Connection,
    local_connection: sqlite3.Connection,
    api: FakeAmuleApi,
    downloading: bool,
) -> AmuleWorks:
    """The factory over every work of one client, as the composition builds it."""
    wall_clock, monotonic_clock = FakeTime().wall, api.monotonic_clock
    observability = ObservabilityOverFakes()
    later = PartsBuiltLater()
    later.health_recorder = HealthRecorder(logger=FakeLogger(), subscribers=())
    observation_store = SqliteObservationStore(catalog_connection)
    decision_store = SqliteDecisionStore(catalog_connection)
    targets = read_targets(_FIXTURES / "golden_targets.yaml")
    engine = MatchingEngine(
        read_matcher_config(_REPOSITORY_ROOT / "deploy" / "matcher.yml"),
        targets=targets,
        max_filename_length=4096,
    )
    backoff_state_store = FakeBackoffStateStore()
    backoff = BackoffRegistry(
        BackoffPolicy(base_seconds=60.0, cap_seconds=600.0, factor=2.0, jitter_ratio=0.0),
        wall_clock=wall_clock,
        monotonic_clock=monotonic_clock,
        jitter_generator=FakeJitterGenerator(),
        backoff_state_reader=backoff_state_store,
    )
    channels = _client(FakeAmuleApi()).channels()
    download_config = DownloadConfig(
        poll_interval_seconds=30.0,
        min_free_bytes=0,
        lost_after=timedelta(days=1),
        output_directory=str(tmp_path),
        reappeared_after=timedelta(hours=12),
        sources_interval=timedelta(minutes=5),
    )
    return AmuleWorks(
        client_name=_AMULED,
        keywords=_KEYWORDS,
        client_component=client_component(_AMULED),
        status_sensor_component=status_sensor_component(_AMULED),
        channel_components={
            channel: channel_component(client_name=_AMULED, channel=channel) for channel in channels
        },
        keyword_components={
            (channel, keyword): keyword_search_component(
                keyword=keyword, client_name=_AMULED, channel=channel
            )
            for channel in channels
            for keyword in _KEYWORDS
        },
        download_steps=download_steps(
            download_config,
            tracking=download_tracking_component(_AMULED),
            source_tracking=source_tracking_component(_AMULED),
            targets=targets,
            local_connection=local_connection,
            catalog_connection=catalog_connection,
            observation_store=observation_store,
            decision_store=decision_store,
            waker=FakeWaker(),
            wall_clock=wall_clock,
            monotonic_clock=monotonic_clock,
            observability_dispatcher=observability.dispatcher,
            record_outcome=later.record,
            node_id=NodeId("n1"),
        )
        if downloading
        else None,
        backoff=backoff,
        backoff_saver=BackoffSaver(
            backoff=backoff, backoff_state_writer=backoff_state_store, logger=FakeLogger()
        ),
        cataloguer=Cataloguer(
            observation_writer=observation_store,
            file_judge=FileJudge(
                observation_reader=observation_store,
                decision_writer=decision_store,
                decision_reader=decision_store,
                engine=engine,
                waker=FakeWaker(),
                observability_dispatcher=observability.dispatcher,
                wall_clock=wall_clock,
                node_id=NodeId("n1"),
            ),
            observability_dispatcher=observability.dispatcher,
            wall_clock=wall_clock,
            node_id=NodeId("n1"),
            logger=FakeLogger(),
        ),
        observability_dispatcher=observability.dispatcher,
        status_reading_writer=InMemoryStatusReadingStore((_AMULED,)),
        parts_built_later=later,
        wall_clock=wall_clock,
        monotonic_clock=monotonic_clock,
        time_limits=AmuleTurnTimeLimits(
            request_bound=timedelta(seconds=60),
            search_budget=timedelta(seconds=120),
            notification_timeout=timedelta(seconds=5),
            keywords=_KEYWORDS,
        ),
    )


def _fed(works: list[SupervisedWork]) -> set[Component]:
    return {component for supervised in works for component in supervised.feeds}


@pytest.fixture(params=[True, False], ids=["downloading", "cataloguing"])
def downloading(request: pytest.FixtureRequest) -> bool:
    return bool(request.param)


async def test_each_owner_s_components_are_those_its_works_feed_every_feed_owned(
    *,
    tmp_path: Path,
    catalog_connection: sqlite3.Connection,
    local_connection: sqlite3.Connection,
    downloading: bool,
) -> None:
    api = FakeAmuleApi()
    amule = _amule_works(
        tmp_path=tmp_path,
        catalog_connection=catalog_connection,
        local_connection=local_connection,
        api=api,
        downloading=downloading,
    )
    webui = WebuiWorks(component=webui_component(), monotonic_clock=api.monotonic_clock)
    notifier = notifier_components(
        apprise_notifier(_TARGETS, apprise_factory=FakeApprise).services()
    )
    owners = {name: FakeStateOwner(name) for name in ("amule", "webui", "notifier")}

    mapping = component_owners(
        amule_works=amule,
        amule_owner=owners["amule"],
        webui_works=webui,
        webui_owner=owners["webui"],
        notifier_components=notifier.values(),
        notifier_owner=owners["notifier"],
    )

    amule_fed = _fed(amule.over(_client(api)))
    webui_fed = _fed(webui.over(lambda: True))
    assert {c for c, owner in mapping.items() if owner is owners["amule"]} == amule_fed
    assert {c for c, owner in mapping.items() if owner is owners["webui"]} == webui_fed
    assert {c for c, owner in mapping.items() if owner is owners["notifier"]} == set(
        notifier.values()
    )
    assert len(amule_fed) == 2 * len(_KEYWORDS) + 2 + 1 + (2 if downloading else 0)


async def test_a_rebuilt_client_s_works_run_their_turns_on_the_new_client_alone(
    *,
    tmp_path: Path,
    catalog_connection: sqlite3.Connection,
    local_connection: sqlite3.Connection,
) -> None:
    first, rebuilt = FakeAmuleApi(), FakeAmuleApi()
    amule = _amule_works(
        tmp_path=tmp_path,
        catalog_connection=catalog_connection,
        local_connection=local_connection,
        api=rebuilt,
        downloading=True,
    )
    amule.over(_client(first))

    asked: list[int] = []
    for supervised in amule.over(_client(rebuilt)):
        before = len(rebuilt.requests)
        await supervised.work.run_once()
        asked.append(len(rebuilt.requests) - before)

    assert first.requests == []
    assert all(asked), asked  # each work's turn asked the rebuilt client


async def test_a_rebuilt_webui_s_liveness_watches_the_new_thread() -> None:
    webui = WebuiWorks(component=webui_component(), monotonic_clock=FakeAmuleApi().monotonic_clock)
    webui.over(lambda: False)
    [liveness] = webui.over(lambda: True)
    await liveness.work.run_once()  # a fallen thread would raise WebuiFallen


async def test_a_rebuilt_notifier_lists_the_services_its_components_name() -> None:
    first = apprise_notifier(_TARGETS, apprise_factory=FakeApprise)
    components = notifier_components(first.services())
    rebuilt = apprise_notifier(_TARGETS, apprise_factory=FakeApprise)
    assert tuple(components) == rebuilt.services()


_TARGETS = (
    NotificationTarget(url="discord://a/b", audience=Audience.COMMUNITY, node_prefix=True),
    NotificationTarget(url="discord://c/d", audience=Audience.COMMUNITY, node_prefix=True),
    NotificationTarget(url="ntfy://e", audience=Audience.OPERATIONS, node_prefix=False),
)

"""A channel refused for ~4 days at the shipped backoff makes run_task raise OverflowError."""

from datetime import timedelta

import pytest

from p2pwatch.application.steps.backoff_registry import BackoffPolicy, BackoffRegistry
from p2pwatch.application.steps.search_worker import SearchTask, SearchWorker
from p2pwatch.domain.identifiers import Channel, ClientName, Keyword, NodeId
from p2pwatch.domain.search.backoff import BackoffKey
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore
from tests.fakes.adapters.driven.fake_jitter_generator import FakeJitterGenerator
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_search_client import FakeSearchClient, make_search_failed
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes

# The values docs/migration-4x.md shows for search.backoff.
_POLICY = BackoffPolicy(base_seconds=2.0, cap_seconds=300.0, factor=2.0, jitter_ratio=0.0)
_FAILURES = 1100


@pytest.mark.asyncio
async def test_a_channel_refused_for_days_ends_the_search_task() -> None:
    fake_time = FakeTime()
    registry = BackoffRegistry(
        _POLICY,
        wall_clock=fake_time.wall,
        monotonic_clock=fake_time.monotonic,
        jitter_generator=FakeJitterGenerator(),
        backoff_state_reader=FakeBackoffStateStore(),
    )
    client = FakeSearchClient(search_failures=[make_search_failed()] * _FAILURES)
    worker = SearchWorker(
        client_name=ClientName("amuled"),
        client=client,
        backoff=registry,
        cataloguer=None,  # type: ignore[arg-type]  # never reached on a failed search
        observability_dispatcher=ObservabilityOverFakes().dispatcher,
        logger=FakeLogger(),
    )
    task = SearchTask(keyword=Keyword("keroro"), channel=Channel("ed2k"))
    elapsed = timedelta(0)
    with pytest.raises(OverflowError):
        for attempt in range(1, _FAILURES + 1):
            wait = worker.time_until_ready(Channel("ed2k"))
            fake_time.advance(wait)
            elapsed += wait
            await worker.run_task(task, node_id=NodeId("n1"))
    print(f"OverflowError at attempt {attempt}, after {elapsed} of refusals")
    key = BackoffKey(client_name=ClientName("amuled"), channel=Channel("ed2k"))
    assert registry.snapshot()[key].attempts == attempt - 1

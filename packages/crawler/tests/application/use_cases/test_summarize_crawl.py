"""``SummarizeCrawl``: the dashboard's clients, crawl, node and target coverage, in one read."""

from collections.abc import Mapping
from datetime import UTC, datetime

from p2pwatch.application.ports.driving.crawl_summarizer import ClientSummary, CrawlSummary
from p2pwatch.application.use_cases.summarize_crawl import SummarizeCrawl
from p2pwatch.domain.coverage import TargetCoverage
from p2pwatch.domain.node_state import NodeState
from p2pwatch.domain.status_reading import READING_FRESH_FOR, PublishedReading, StatusReading
from tests.fakes.adapters.driven.fake_client_status_store import FakeClientStatusStore
from tests.fakes.adapters.driven.fake_coverage_reader import FakeCoverageReader
from tests.fakes.adapters.driven.fake_node_state_reader import FakeNodeStateReader
from tests.fakes.adapters.driven.fake_run_state import FakeRunState
from tests.fakes.adapters.driven.fake_time import FakeTime

_NODE_STATE = NodeState(node_id="node-1", created_at=None, downloads=(), backoff_state_by_key={})
_READING = StatusReading(read_at=datetime(2026, 10, 14, tzinfo=UTC), status=None)


def _summarize(
    *,
    target_ids: tuple[str, ...] = (),
    tiers_by_target: Mapping[str, tuple[str, ...]] | None = None,
    published_readings: Mapping[str, PublishedReading | None] | None = None,
    paused: bool = False,
    fake_time: FakeTime | None = None,
) -> CrawlSummary:
    return SummarizeCrawl(
        target_ids=target_ids,
        coverage_reader=FakeCoverageReader(tiers_by_target or {}),
        node_state_reader=FakeNodeStateReader(_NODE_STATE),
        run_state_reader=FakeRunState(paused=paused),
        client_status_reader=FakeClientStatusStore(published_readings),
        monotonic_clock=(fake_time or FakeTime()).monotonic,
    ).summarize_crawl()


def test_each_configured_target_has_its_coverage_in_their_order() -> None:
    summary = _summarize(
        target_ids=("062B", "062A"),
        tiers_by_target={"062A": ("download",), "999Z": ("notify",)},
    )

    assert summary.target_coverages == (
        TargetCoverage("062B", status="none", best_tier=None, file_count=0),
        TargetCoverage("062A", status="found", best_tier="download", file_count=1),
    )


def test_the_summary_holds_the_node_state_and_whether_the_crawl_is_paused() -> None:
    assert _summarize(paused=True).node_state == _NODE_STATE
    assert _summarize(paused=True).is_paused
    assert not _summarize(paused=False).is_paused


def test_a_reading_is_fresh_until_it_is_older_than_its_freshness() -> None:
    fake_time = FakeTime()
    published_at = fake_time.monotonic.now()
    fake_time.advance(READING_FRESH_FOR)
    published_readings = {
        "never": None,
        "fresh": PublishedReading(_READING, published_at),
        "stale": PublishedReading(_READING, published_at - READING_FRESH_FOR / 2),
    }

    summary = _summarize(published_readings=published_readings, fake_time=fake_time)

    assert summary.client_summaries == (
        ClientSummary("never", reading=None, is_fresh=False),
        ClientSummary("fresh", reading=_READING, is_fresh=True),
        ClientSummary("stale", reading=_READING, is_fresh=False),
    )

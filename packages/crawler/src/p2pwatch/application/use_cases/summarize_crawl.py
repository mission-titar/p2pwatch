"""Summarizes the crawl from the catalog, local.db, the run state and the clients' readings."""

from p2pwatch.application.ports.driven.client_status_reader import StatusReadingReader
from p2pwatch.application.ports.driven.coverage_reader import CoverageReader
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.node_state_reader import NodeStateReader
from p2pwatch.application.ports.driven.run_state_reader import RunStateReader
from p2pwatch.application.ports.driving.crawl_summarizer import (
    ClientSummary,
    CrawlSummarizer,
    CrawlSummary,
)
from p2pwatch.domain.coverage import coverage_of
from p2pwatch.domain.status_reading import is_reading_fresh


class SummarizeCrawl(CrawlSummarizer):
    """A reading's age is measured on the monotonic clock, which no wall clock step moves."""

    def __init__(
        self,
        *,
        target_ids: tuple[str, ...],
        coverage_reader: CoverageReader,
        node_state_reader: NodeStateReader,
        run_state_reader: RunStateReader,
        status_reading_reader: StatusReadingReader,
        monotonic_clock: MonotonicClock,
    ) -> None:
        self._target_ids = target_ids
        self._coverage_reader = coverage_reader
        self._node_state_reader = node_state_reader
        self._run_state_reader = run_state_reader
        self._status_reading_reader = status_reading_reader
        self._monotonic_clock = monotonic_clock

    def summarize_crawl(self) -> CrawlSummary:
        published_readings = self._status_reading_reader.read_readings()
        now = self._monotonic_clock.now()
        tiers_by_target = self._coverage_reader.read_target_coverage()
        return CrawlSummary(
            client_summaries=tuple(
                ClientSummary(
                    client_name,
                    reading=None if published is None else published.reading,
                    is_fresh=published is not None
                    and is_reading_fresh(now - published.published_at),
                )
                for client_name, published in published_readings.items()
            ),
            is_paused=self._run_state_reader.is_paused(),
            node_state=self._node_state_reader.read_node_state(),
            target_coverages=tuple(
                coverage_of(target_id, tiers_by_target.get(target_id, ()))
                for target_id in self._target_ids
            ),
        )

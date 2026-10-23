"""Pauses the crawl by pausing its run state."""

from p2pwatch.application.ports.driven.run_state_writer import RunStateWriter
from p2pwatch.application.ports.driving.crawl_pauser import CrawlPauser


class PauseCrawl(CrawlPauser):
    """The run state changes on the crawler's loop, after the call has returned."""

    def __init__(self, run_state: RunStateWriter) -> None:
        self._run_state = run_state

    def pause_crawl(self) -> None:
        self._run_state.set_paused(True)

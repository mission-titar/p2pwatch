"""``CrawlSummarizer``: summarizes the crawl, for the dashboard."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from p2pwatch.domain.coverage import TargetCoverage
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.node_state import NodeState
from p2pwatch.domain.status_reading import StatusReading


@dataclass(frozen=True)
class ClientSummary:
    """A client's latest status reading, ``None`` before its first; stale, it is not fresh."""

    client_name: ClientName
    reading: StatusReading | None
    is_fresh: bool


@dataclass(frozen=True)
class CrawlSummary:
    client_summaries: tuple[ClientSummary, ...]
    is_paused: bool
    node_state: NodeState
    target_coverages: tuple[TargetCoverage, ...]  # one per configured target, in their order


class CrawlSummarizer(ABC):
    """Summarizes the crawl, from any thread."""

    @abstractmethod
    def summarize_crawl(self) -> CrawlSummary:
        """Each client's status, whether the crawl is paused, the node, each target's coverage."""

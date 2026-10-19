"""What the crawler expects from any client that searches; its errors are in ``client_errors``.

Protocol stubs stay on ONE line: a body on a second one is an uncovered branch.
"""

from dataclasses import dataclass
from typing import Protocol

from p2pwatch.domain.observation import FileObservation


@dataclass(frozen=True)
class SearchAnswer:
    """What one search found, and how many of its results the client could not read."""

    observations: tuple[FileObservation, ...]
    skipped_result_count: int


class SearchClient(Protocol):
    """``channels`` are opaque names the core never tests. ``search`` returns once the client
    signals the end, or ``budget_seconds`` after the search's network start at the latest."""

    channels: tuple[str, ...]

    async def search(self, keyword: str, channel: str, budget_seconds: float) -> SearchAnswer: ...

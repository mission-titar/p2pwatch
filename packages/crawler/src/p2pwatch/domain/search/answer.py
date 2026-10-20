"""What a client answers to one search."""

from dataclasses import dataclass

from p2pwatch.domain.observation import ReportedFile


@dataclass(frozen=True)
class SearchAnswer:
    """What one search found, and how many of its results the client could not read."""

    reported_files: tuple[ReportedFile, ...]
    skipped_result_count: int

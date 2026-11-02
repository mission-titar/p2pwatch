"""A catalogued file's history: its observations over an interval and its current decisions."""

from dataclasses import dataclass

from catalog_matching.domain.engine import DecisionRecord
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.file_target_decision import DatedDecision
from p2pwatch.domain.observation import FileObservation


@dataclass(kw_only=True, frozen=True)
class FileHistory:
    """A file, its size, its observations over an interval, its latest one over any, its current
    decisions, the legacy retraction of no target left out."""

    file: FileKey
    size_bytes: int
    observations: tuple[FileObservation, ...]  # oldest first
    latest_observation: FileObservation | None
    decisions: tuple[DatedDecision[DecisionRecord], ...]  # one per target in target order
    known_filenames: tuple[str, ...]  # each filename it was seen under, once, sorted

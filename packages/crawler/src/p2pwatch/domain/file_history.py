"""A catalogued file's history: its observations over an interval and its current decisions."""

from dataclasses import dataclass

from catalog_matching.domain.engine import DecisionRecord
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.file_target_decision import DatedDecision
from p2pwatch.domain.observation import FileObservation


@dataclass(kw_only=True, frozen=True)
class FileHistory:
    """A file, the size it was first observed with, its observations over an interval, oldest
    first, its latest one over any, its current decisions, one per target in target order (the
    legacy ``target_id=""`` sentinel is none), and each filename it was seen under, once."""

    file: FileKey
    size_bytes: int
    observations: tuple[FileObservation, ...]
    latest_observation: FileObservation | None
    decisions: tuple[DatedDecision[DecisionRecord], ...]
    known_filenames: tuple[str, ...]  # sorted

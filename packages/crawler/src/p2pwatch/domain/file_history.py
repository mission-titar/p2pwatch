"""A catalogued file's history: its observations over an interval and its current decisions."""

from dataclasses import dataclass
from datetime import datetime

from catalog_matching.domain.engine import DecisionRecord
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.observation import FileObservation


@dataclass(frozen=True)
class DatedDecision:
    """A decision, the instant it was made and the node that made it; apart from
    ``DecisionRecord``, whose equality the anti-redundancy compares on its three fields."""

    decision: DecisionRecord
    decided_at: datetime
    node_id: str


@dataclass(frozen=True)
class FileHistory:
    """A file's observations over an interval, oldest first, its latest one over any, its
    current decisions, one per target in target order, and every filename it was seen under."""

    file: FileKey
    size_bytes: int
    observations: tuple[FileObservation, ...]
    latest_observation: FileObservation | None
    decisions: tuple[DatedDecision, ...]
    known_filenames: tuple[str, ...]  # sorted

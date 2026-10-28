"""Observation of a file seen on the network. PURE domain.

``raw_metadata`` is the per-network catch-all of ``(name, value)`` pairs: no metadata field is lost.
"""

from dataclasses import dataclass
from datetime import datetime

from catalog_matching.domain.models import FileCandidate
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.identifiers import Keyword, NodeId

RawMetadata = tuple[tuple[str, str | int | None], ...]

# DECISION 8: the "MB" shown by eMule clients are binary (MiB).
_BYTES_PER_MIB = 1024 * 1024


def candidate_from_fields(
    filename: str,
    size_bytes: int,
    duration_seconds: int | None,
    bitrate_kbps: int | None,
) -> FileCandidate:
    """Bridge to the matching engine: unit conversions (bytes -> MiB, int -> float).

    Single source of the conversion (spec re-evaluation §6): ``ReportedFile.to_candidate`` (the
    live path and the re-evaluation) and the matching explainer call this.
    """
    duration = float(duration_seconds) if duration_seconds is not None else None
    bitrate = float(bitrate_kbps) if bitrate_kbps is not None else None
    return FileCandidate(
        filename=filename,
        size_mib=size_bytes / _BYTES_PER_MIB,
        duration_seconds=duration,
        bitrate_kbps=bitrate,
    )


def fold_raw_metadata(
    raw_metadata: tuple[tuple[str, str], ...],
    codec: str | None,
    file_type: str | None,
    complete_source_count: int,
) -> RawMetadata:
    """``raw_metadata`` with the three eD2k-only fields appended, absent ones as ``None``. The
    amuleapi mapper and the catalog migration share it, so both store the same pairs."""
    return (
        *raw_metadata,
        ("codec", codec),
        ("file_type", file_type),
        ("complete_source_count", complete_source_count),
    )


@dataclass(frozen=True)
class ReportedFile:
    """A file a search reported, whose result names no source; ``keyword`` is its provenance.
    Media fields are ``None`` when the network did not report them (self-declared, unreliable)."""

    file: FileKey
    filename: str
    size_bytes: int
    source_count: int
    keyword: Keyword
    duration_seconds: int | None = None
    bitrate_kbps: int | None = None
    raw_metadata: RawMetadata = ()

    def to_candidate(self) -> FileCandidate:
        """Bridge to the matching engine (delegates to ``candidate_from_fields``)."""
        return candidate_from_fields(
            self.filename, self.size_bytes, self.duration_seconds, self.bitrate_kbps
        )


@dataclass(frozen=True)
class FileObservation:
    """A reported file and the instant the crawler learned of it, which the network never dates,
    by the node ``node_id``."""

    reported_file: ReportedFile
    observed_at: datetime
    node_id: NodeId

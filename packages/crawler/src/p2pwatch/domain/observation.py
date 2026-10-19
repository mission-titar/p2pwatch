"""Observation of a file seen on the network. PURE domain.

``raw_meta`` is the per-network catch-all of ``(name, value)`` pairs: no metadata field is lost.
"""

from dataclasses import dataclass
from datetime import datetime

from catalog_matching.domain.models import FileCandidate
from p2pwatch.domain.file_key import FileKey

RawMeta = tuple[tuple[str, str | int | None], ...]

# DECISION 8: the "MB" shown by eMule clients are binary (MiB).
_BYTES_PER_MIB = 1024 * 1024


def candidate_from_fields(
    filename: str,
    size_bytes: int,
    duration_seconds: int | None,
    bitrate_kbps: int | None,
) -> FileCandidate:
    """Bridge to the matching engine: unit conversions (bytes -> MiB, int -> float).

    Single source of the conversion (spec re-evaluation §6): both ``ReportedFile.
    to_candidate`` (live path) and the re-evaluation (``ReevalRow`` ->
    candidate) call this.
    """
    duration = float(duration_seconds) if duration_seconds is not None else None
    bitrate = float(bitrate_kbps) if bitrate_kbps is not None else None
    return FileCandidate(
        filename=filename,
        size_mib=size_bytes / _BYTES_PER_MIB,
        duration_seconds=duration,
        bitrate_kbps=bitrate,
    )


def fold_raw_meta(
    raw_meta: tuple[tuple[str, str], ...],
    codec: str | None,
    file_type: str | None,
    complete_source_count: int,
) -> RawMeta:
    """``raw_meta`` with the three eD2k-only fields appended, absent ones as ``None``. The
    amuleapi mapper and the catalog migration share it, so both store the same pairs."""
    return (
        *raw_meta,
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
    keyword: str
    duration_seconds: int | None = None
    bitrate_kbps: int | None = None
    raw_meta: RawMeta = ()

    def to_candidate(self) -> FileCandidate:
        """Bridge to the matching engine (delegates to ``candidate_from_fields``)."""
        return candidate_from_fields(
            self.filename, self.size_bytes, self.duration_seconds, self.bitrate_kbps
        )


@dataclass(frozen=True)
class FileObservation:
    """A reported file and the instant the crawler learned of it, which the network never dates."""

    reported_file: ReportedFile
    observed_at: datetime


@dataclass(frozen=True)
class Sighting:
    """A file seen once: one observation."""

    file: FileKey
    filename: str
    observed_at: str
    source_count: int
    size_bytes: int
    duration_seconds: int | None
    bitrate_kbps: int | None
    keyword: str

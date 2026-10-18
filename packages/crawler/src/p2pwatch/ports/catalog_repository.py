"""``CatalogRepository`` port: the catalog's durable memory (spec data-model §4).

SYNCHRONOUS Protocol (spec §3: a local write is sub-millisecond; if plan C wants to
isolate itself, it will wrap it in ``asyncio.to_thread`` without touching this layer).
The port imports ONLY the domain. Each stub's ``...`` ends its ``def`` (which runs at class
creation: covered). The use-case gives each write its instant (``observed_at``/``decided_at``),
the adapter stamps ``node_id``: ``record_decision`` receives the file key and the instant ALONGSIDE
the decision (``MatchDecision`` carries neither: a domain without persistence columns).
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from catalog_matching.domain.engine import DecisionRecord, MatchDecision
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.observation import FileObservation


@dataclass(frozen=True)
class ObservedFile:
    """Minimal READ shape of an observation: name + size (to build an ed2k link).

    The download loop (spec §5) reads the LATEST observation of a hash to rebuild its ed2k
    link (``build_ed2k_link(filename, size_bytes, hash)``). We return only the two required
    fields — not the whole ``FileObservation`` (the rest is useless for download).
    """

    filename: str
    size_bytes: int


@dataclass(frozen=True)
class DownloadCandidate:
    """A file whose latest verdict for ``target_id`` is tier=download, for the download loop."""

    file: FileKey
    target_id: str


@dataclass(frozen=True)
class ReevalRow:
    """One file's latest observation, enough to rebuild a :class:`FileCandidate`.

    Read by the re-evaluation (spec re-evaluation §6): each row feeds
    ``domain.observation.candidate_from_fields`` to re-run the matching engine against
    the whole catalogue, one row per catalogued file.
    """

    file: FileKey
    filename: str
    size_bytes: int
    duration_seconds: int | None
    bitrate_kbps: int | None


class CatalogRepository(Protocol):
    """Sync catalog write contract (append-only; the adapter reports, it does not decide).

    ``latest_decisions`` (set-diff anti-redundancy, spec §7) returns the latest
    :class:`DecisionRecord` PER TARGET for a file (including a target whose latest tier is
    ``retracted``; excluding the legacy ``target_id=""`` sentinel), for multi-target matching.
    ``download_candidates`` (spec download §5) returns the :class:`DownloadCandidate` whose
    LATEST verdict is tier=download (to be replayed by the download loop).
    ``latest_observation`` returns the most recent :class:`ObservedFile` of a file (filename
    and size for the ed2k link), or ``None``. ``best_observation`` returns the file's clean
    filename (the most sourced, then the latest) with its size, or ``None``.
    ``iter_reevaluation_rows`` streams every file's latest observation as a :class:`ReevalRow`
    (spec re-evaluation §6), for the startup re-evaluation to rebuild a candidate per file;
    ``count_files`` is its progress total.
    ``known_filenames`` returns every distinct filename of a file, sorted.
    These reads are harmless (no write).
    ``record_retraction`` (spec §7) appends a per-target ``match_decisions`` row
    (``rule_name=""``, ``tier="retracted"``) marking ``target_id`` as no longer matching this
    file: the append-only table has no delete, so exclusion is an appended row.
    """

    def record_observation(self, observation: FileObservation, observed_at: datetime) -> None: ...

    def record_decision(
        self, file: FileKey, decision: MatchDecision, decided_at: datetime
    ) -> None: ...

    def record_retraction(self, file: FileKey, target_id: str, decided_at: datetime) -> None: ...

    def latest_decisions(self, file: FileKey) -> dict[str, DecisionRecord]: ...

    def download_candidates(self) -> tuple[DownloadCandidate, ...]: ...

    def latest_observation(self, file: FileKey) -> ObservedFile | None: ...

    def best_observation(self, file: FileKey) -> ObservedFile | None: ...

    def known_filenames(self, file: FileKey) -> tuple[str, ...]: ...

    def count_files(self) -> int: ...

    def iter_reevaluation_rows(self) -> Iterator[ReevalRow]: ...

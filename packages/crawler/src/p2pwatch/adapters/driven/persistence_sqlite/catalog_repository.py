"""``SqliteCatalogRepository``: ``FileObservation``/``MatchDecision`` → durable rows.

The adapter stores what the domain ignores (data-model spec §3): ``decided_at``, given by the
use-case at each write, and ``node_id``, given with it.
``raw_meta`` is serialized as a JSON LIST of pairs (``[["0x0308", "0"], …]``), wire order and
duplicates preserved, ``ensure_ascii=False``, no sorting (spec §3). ``record_observation`` makes
ONE transaction (spec §4): ``INSERT OR IGNORE`` into ``files`` (first sight wins), into
``observation_variants`` (found by its ``content_hash``) and into ``observations``: the
OBSERVED size is ALWAYS written into the variant (deviation 1, spec §5: a size anomaly must
not become invisible).

The hash canon (32 lowercase hex, v0.5.0 canon) is validated IN PYTHON before the
transaction: ``INSERT OR IGNORE`` silently swallows a CHECK violation (documented
SQLite behavior): without this guard, a non-canonical hash would only be stopped
by the ``foreign_keys`` pragma (opaque diagnostic), and a connection without that
pragma would commit an ORPHAN observation. The rollback catches ``BaseException``
(same discipline as ``connection._open``): a NON-sqlite failure at binding (e.g.
``UnicodeEncodeError`` on a lone surrogate) must not leave the connection
``in_transaction``, otherwise the repository would be permanently broken.
"""

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import suppress
from datetime import datetime

from catalog_matching.domain.engine import DecisionRecord, MatchDecision
from p2pwatch.adapters.driven.persistence_sqlite import observation_read
from p2pwatch.adapters.driven.persistence_sqlite.connection import utc_iso
from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError, wrap_sqlite_errors
from p2pwatch.adapters.driven.persistence_sqlite.variants import content_hash, iso_to_micros
from p2pwatch.domain.download.candidate import DownloadCandidate
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observation import FileObservation
from p2pwatch.domain.retraction import RETRACTED_TIER
from p2pwatch.ports.driven.catalog_scan_reader import CatalogScanReader
from p2pwatch.ports.driven.decision_reader import DecisionReader
from p2pwatch.ports.driven.decision_writer import DecisionWriter
from p2pwatch.ports.driven.observation_reader import ObservationReader
from p2pwatch.ports.driven.observation_writer import ObservationWriter

_CANONICAL_HASH_RE = re.compile(r"[0-9a-f]{32}\Z")

_INSERT_FILE = (
    "INSERT OR IGNORE INTO files (file_id, network, native_id, size_bytes) VALUES (?, ?, ?, ?)"
)

_INSERT_VARIANT = """
INSERT OR IGNORE INTO observation_variants (
    file_id, filename, size_bytes, duration_seconds, bitrate_kbps, raw_meta, keyword, node_id,
    content_hash
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_INSERT_OBSERVATION = """
INSERT OR IGNORE INTO observations (variant_id, observed_at, source_count)
SELECT variant_id, ?, ? FROM observation_variants WHERE content_hash = ?
"""

_INSERT_DECISION = """
INSERT INTO match_decisions (file_id, target_id, rule_name, tier, decided_at, node_id)
VALUES (?, ?, ?, ?, ?, ?)
"""

# Latest verdict per (file_id, target_id) for one file (set-diff anti-redundancy, spec §7).
# ROW_NUMBER per target, order (decided_at, id) DESCENDING (most recent = rank 1); keep rank 1.
# INCLUDES a target whose latest tier is 'retracted' (no tier filter); EXCLUDES the legacy
# target_id='' sentinel (not a real target). The idx_match_decisions_file_target_decided index
# serves the filter.
_SELECT_LAST_DECISIONS = """
SELECT target_id, rule_name, tier FROM (
    SELECT
        target_id, rule_name, tier,
        ROW_NUMBER() OVER (PARTITION BY target_id ORDER BY decided_at DESC, id DESC) AS rn
    FROM match_decisions
    WHERE file_id = ? AND target_id <> ''
) WHERE rn = 1
"""

# Latest verdict per (file_id, target_id), kept when tier=download (download spec §5,
# multi-target §6). Window: ROW_NUMBER per (file_id, target_id), order (decided_at, id)
# DESCENDING (most recent = rank 1); keep rank 1 AND tier='download'. PARTITION BY the FULL
# key so a whole-episode file with BOTH segments in download yields BOTH candidates. Sorted
# by (network, native_id, target_id).
_SELECT_DOWNLOAD_DECISIONS = """
SELECT f.network, f.native_id, d.target_id FROM (
    SELECT
        file_id, target_id, tier,
        ROW_NUMBER() OVER (
            PARTITION BY file_id, target_id ORDER BY decided_at DESC, id DESC
        ) AS rn
    FROM match_decisions
) AS d
JOIN files AS f ON f.file_id = d.file_id
WHERE d.rn = 1 AND d.tier = 'download'
ORDER BY f.network, f.native_id, d.target_id
"""

_COUNT_FILES = "SELECT COUNT(*) FROM files"


class SqliteCatalogRepository(
    ObservationWriter, ObservationReader, DecisionWriter, DecisionReader, CatalogScanReader
):
    """SQLite implementation of the catalog's five ports."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record_observation(self, observation: FileObservation, node_id: str) -> None:
        """ONE transaction: file (first sight wins), its variant, the stamped observation."""
        reported_file = observation.reported_file
        file = reported_file.file
        if not _CANONICAL_HASH_RE.fullmatch(file.native_id):
            raise PersistenceError(f"non-canonical eD2k hash: {file.native_id!r}")
        variant = (
            file.file_id,
            reported_file.filename,
            reported_file.size_bytes,
            reported_file.duration_seconds,
            reported_file.bitrate_kbps,
            json.dumps(reported_file.raw_meta, ensure_ascii=False),
            reported_file.keyword,
            node_id,
        )
        variant_content_hash = content_hash(*variant)
        observed_at_micros = iso_to_micros(utc_iso(observation.observed_at))
        with wrap_sqlite_errors():
            self._connection.execute("BEGIN")
            try:
                self._connection.execute(
                    _INSERT_FILE,
                    (file.file_id, file.network, file.native_id, reported_file.size_bytes),
                )
                self._connection.execute(_INSERT_VARIANT, (*variant, variant_content_hash))
                self._connection.execute(
                    _INSERT_OBSERVATION,
                    (observed_at_micros, reported_file.source_count, variant_content_hash),
                )
                self._connection.execute("COMMIT")
            except BaseException:
                with suppress(sqlite3.Error):
                    self._connection.execute("ROLLBACK")
                raise

    def record_decision(
        self, file: FileKey, decision: MatchDecision, decided_at: datetime, node_id: str
    ) -> None:
        """INSERT alone (autocommit); unknown file → FK violated → ``PersistenceError``.

        Only the 3 columns of ``MatchDecision`` are persisted (engine spec);
        ``explanation`` is runtime explainability, NEVER a column.
        """
        if not _CANONICAL_HASH_RE.fullmatch(file.native_id):
            raise PersistenceError(f"non-canonical eD2k hash: {file.native_id!r}")
        with wrap_sqlite_errors():
            self._connection.execute(
                _INSERT_DECISION,
                (
                    file.file_id,
                    decision.target_id,
                    decision.rule_name,
                    decision.tier,
                    utc_iso(decided_at),
                    node_id,
                ),
            )

    def record_retraction(
        self, file: FileKey, target_id: str, decided_at: datetime, node_id: str
    ) -> None:
        """Appends a per-target ``retracted`` decision (spec §7).

        Mirrors ``record_decision`` (same canonical-hash guard, same autocommit ``INSERT``): a
        file that no longer matches ``target_id`` gets an appended
        ``(target_id, rule_name="", tier=RETRACTED_TIER)`` row instead of a mutation, per the
        append-only invariant. Retracting one target leaves the file's other targets intact.
        Unknown file → FK violated → ``PersistenceError``.
        """
        if not _CANONICAL_HASH_RE.fullmatch(file.native_id):
            raise PersistenceError(f"non-canonical eD2k hash: {file.native_id!r}")
        with wrap_sqlite_errors():
            self._connection.execute(
                _INSERT_DECISION,
                (
                    file.file_id,
                    target_id,
                    "",
                    RETRACTED_TIER,
                    utc_iso(decided_at),
                    node_id,
                ),
            )

    def read_latest_decisions(self, file: FileKey) -> dict[str, DecisionRecord]:
        """Latest verdict per target for this file (set-diff anti-redundancy, spec §7), READ.

        Maps ``target_id`` → its latest :class:`DecisionRecord`. INCLUDES a target whose latest
        tier is ``retracted`` (the application's set-diff skips re-retracting it); EXCLUDES the
        legacy ``target_id=""`` sentinel. The hash is NOT validated canonical (harmless read: a
        non-canonical hash matches nothing → ``{}``).
        """
        with wrap_sqlite_errors():
            rows = self._connection.execute(_SELECT_LAST_DECISIONS, (file.file_id,)).fetchall()
        return {
            row[0]: DecisionRecord(target_id=row[0], rule_name=row[1], tier=row[2]) for row in rows
        }

    def read_download_candidates(self) -> tuple[DownloadCandidate, ...]:
        """``(file, target_id)`` whose LATEST verdict is tier=download, to replay (download §5).

        Keyed per ``(file, target_id)``: a whole-episode file matching both segments now yields
        MULTIPLE :class:`DownloadCandidate` for the SAME file (one per target). READ.
        """
        with wrap_sqlite_errors():
            rows = self._connection.execute(_SELECT_DOWNLOAD_DECISIONS).fetchall()
        return tuple(
            DownloadCandidate(file=FileKey(Network(row[0]), row[1]), target_id=row[2])
            for row in rows
        )

    def read_latest_observation(self, file: FileKey) -> FileObservation | None:
        """The file's latest observation, or ``None`` (read)."""
        with wrap_sqlite_errors():
            return observation_read.latest_observation(self._connection, file)

    def read_best_observation(self, file: FileKey) -> FileObservation | None:
        """The observation of the clean filename (most sources, then latest), or ``None``."""
        with wrap_sqlite_errors():
            return observation_read.best_observation(self._connection, file)

    def read_known_filenames(self, file: FileKey) -> tuple[str, ...]:
        """Every distinct filename this file was observed under, sorted (read)."""
        with wrap_sqlite_errors():
            return observation_read.known_filenames(self._connection, file)

    def read_file_count(self) -> int:
        """Number of catalogued files, the re-evaluation progress total (read)."""
        with wrap_sqlite_errors():
            row = self._connection.execute(_COUNT_FILES).fetchone()
        return int(row[0])

    def iter_latest_observations(self) -> Iterator[FileObservation]:
        """Every seen file's latest observation, streamed (spec re-evaluation §6)."""
        with wrap_sqlite_errors():
            yield from observation_read.iter_latest_observations(self._connection)

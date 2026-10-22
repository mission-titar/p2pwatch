"""``SqliteCatalogRepository``: ``FileObservation`` → durable rows, and the catalog's scan.

The adapter stores what the domain ignores (data-model spec §3): ``node_id``, given at each write.
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
import sqlite3
from collections.abc import Iterator
from contextlib import suppress

from p2pwatch.adapters.driven.persistence_sqlite import observation_read
from p2pwatch.adapters.driven.persistence_sqlite.canonical_native_id import (
    require_canonical_native_id,
)
from p2pwatch.adapters.driven.persistence_sqlite.connection import utc_iso
from p2pwatch.adapters.driven.persistence_sqlite.errors import wrap_sqlite_errors
from p2pwatch.adapters.driven.persistence_sqlite.variants import content_hash, iso_to_micros
from p2pwatch.application.ports.driven.catalog_scan_reader import CatalogScanReader
from p2pwatch.application.ports.driven.observation_reader import ObservationReader
from p2pwatch.application.ports.driven.observation_writer import ObservationWriter
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.observation import FileObservation

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

_COUNT_FILES = "SELECT COUNT(*) FROM files"


class SqliteCatalogRepository(ObservationWriter, ObservationReader, CatalogScanReader):
    """SQLite implementation of the observations' ports and the catalog's scan."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record_observation(self, observation: FileObservation, node_id: str) -> None:
        """ONE transaction: file (first sight wins), its variant, the stamped observation."""
        reported_file = observation.reported_file
        file = reported_file.file
        require_canonical_native_id(file)
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

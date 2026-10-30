"""``SqliteObservationStore``: ``FileObservation`` → durable rows, and their reads.

The adapter stores what the domain ignores (data-model spec §3): ``node_id``, given at each write.
``raw_metadata`` is serialized as a JSON LIST of pairs (``[["0x0308", "0"], …]``), wire order and
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
(same discipline as ``connection._open``): a NON-sqlite failure at binding must not
leave the connection ``in_transaction``, otherwise the store would be permanently broken.
"""

import json
import sqlite3
from contextlib import suppress

from p2pwatch.adapters.driven.persistence_sqlite import observation_read
from p2pwatch.adapters.driven.persistence_sqlite.canonical_native_id import (
    require_canonical_native_id,
)
from p2pwatch.adapters.driven.persistence_sqlite.errors import wrap_sqlite_errors
from p2pwatch.adapters.driven.persistence_sqlite.micros import instant_to_micros
from p2pwatch.adapters.driven.persistence_sqlite.variants import content_hash
from p2pwatch.application.ports.driven.observation_reader import ObservationReader
from p2pwatch.application.ports.driven.observation_writer import ObservationWriter
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.observation import FileObservation

_INSERT_FILE = (
    "INSERT OR IGNORE INTO files (file_id, network, native_id, size_bytes) VALUES (?, ?, ?, ?)"
)

_INSERT_VARIANT = """
INSERT OR IGNORE INTO observation_variants (
    file_id, filename, size_bytes, duration_seconds, bitrate_kbps, raw_metadata, keyword, node_id,
    content_hash
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_INSERT_OBSERVATION = """
INSERT OR IGNORE INTO observations (variant_id, observed_at_micros, source_count)
SELECT variant_id, ?, ? FROM observation_variants WHERE content_hash = ?
"""


class SqliteObservationStore(ObservationWriter, ObservationReader):
    """SQLite implementation of the observations' ports."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record_observation(self, observation: FileObservation) -> None:
        """ONE transaction: file (first sight wins), its variant, the stamped observation."""
        reported_file = observation.reported_file
        file = reported_file.file
        require_canonical_native_id(file)
        raw_metadata = json.dumps(reported_file.raw_metadata, ensure_ascii=False)
        variant = (
            file.file_id,
            reported_file.filename,
            reported_file.size_bytes,
            reported_file.duration_seconds,
            reported_file.bitrate_kbps,
            raw_metadata,
            reported_file.keyword,
            observation.node_id,
        )
        variant_content_hash = content_hash(
            file_ref=file.file_id,
            filename=reported_file.filename,
            size_bytes=reported_file.size_bytes,
            duration_seconds=reported_file.duration_seconds,
            bitrate_kbps=reported_file.bitrate_kbps,
            raw_metadata=raw_metadata,
            keyword=reported_file.keyword,
            node_id=observation.node_id,
        )
        observed_at_micros = instant_to_micros(observation.observed_at)
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
            return observation_read.latest_observation(self._connection, file=file)

    def read_best_observation(self, file: FileKey) -> FileObservation | None:
        """The observation of the clean filename (most sources, then latest), or ``None``."""
        with wrap_sqlite_errors():
            return observation_read.best_observation(self._connection, file=file)

    def read_known_filenames(self, file: FileKey) -> tuple[str, ...]:
        """Every distinct filename this file was observed under, sorted (read)."""
        with wrap_sqlite_errors():
            return observation_read.known_filenames(self._connection, file=file)

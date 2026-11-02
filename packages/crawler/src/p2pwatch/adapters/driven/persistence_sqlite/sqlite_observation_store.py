"""``SqliteObservationStore``: ``FileObservation`` → durable rows, and their reads.

The adapter stores what the domain ignores (data-model spec §3): ``node_id``, given at each write.
``raw_metadata`` is stored as its ``JsonObjectText``'s canonical text. ``record_observation`` makes
ONE transaction (spec §4): it inserts into ``files`` (first sight wins, and with it the file's
size, which no variant holds), into ``observation_variants`` (found by its ``content_hash``) and
into ``observations``, each ``ON CONFLICT (<key>) DO NOTHING``, which ignores a duplicate key and
raises on any other refusal.

The hash canon (32 lowercase hex, v0.5.0 canon) is validated IN PYTHON before the
transaction, so that its error names the hash. The rollback catches ``BaseException``
(same discipline as ``connection._open``): a NON-sqlite failure at binding must not
leave the connection ``in_transaction``, otherwise the store would be permanently broken.
"""

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
    "INSERT INTO files (file_id, network, native_id, size_bytes) VALUES (?, ?, ?, ?)"
    " ON CONFLICT (file_id) DO NOTHING"
)

_INSERT_VARIANT = """
INSERT INTO observation_variants (
    file_id, filename, duration_seconds, bitrate_kbps, raw_metadata, keyword, node_id, content_hash
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (content_hash) DO NOTHING
"""

_INSERT_OBSERVATION = """
INSERT INTO observations (variant_id, observed_at_micros, source_count)
SELECT variant_id, ?, ? FROM observation_variants WHERE content_hash = ?
ON CONFLICT (variant_id, observed_at_micros, source_count) DO NOTHING
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
        raw_metadata = reported_file.raw_metadata.text
        variant = (
            file.file_id,
            reported_file.filename,
            reported_file.duration_seconds,
            reported_file.bitrate_kbps,
            raw_metadata,
            reported_file.keyword,
            observation.node_id,
        )
        variant_content_hash = content_hash(
            file_ref=file.file_id,
            filename=reported_file.filename,
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

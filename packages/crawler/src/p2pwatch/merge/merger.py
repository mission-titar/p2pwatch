"""``merge_catalogs``: idempotent merge of N ``catalog.db`` into a single output.

Mechanism (merge spec §3/§4): the output is created/opened via ``open_catalog`` (the catalog
migrations, NO duplicated DDL). For each source: we ``ATTACH`` it (outside a transaction),
then INSIDE an explicit transaction (``BEGIN``…``COMMIT``, best-effort ``ROLLBACK`` on error)
we copy its tables in **FK order** (identities first), then ``COMMIT`` and ``DETACH``. A half-copied
source is never committed; a failed merge is re-run safely.

Idempotence (spec §4):
- ``files`` (global content PK) → ``INSERT OR IGNORE`` (first sighting
  wins); NEVER ``OR REPLACE`` (= DELETE + INSERT → collides with the append-only trigger).
- ``observation_variants`` → ``INSERT OR IGNORE`` on its ``content_hash`` (the output
  numbers its own ``variant_id``), then ``observations`` mapped to the output's variant by
  ``content_hash``, ``INSERT OR IGNORE`` on their full key (stage 1, D4).
- ``match_decisions`` (LOCAL ``id``, no global meaning) → explicit columns WITHOUT ``id`` (the
  DB reassigns the ``id``) + dedup by **full natural key** via ``WHERE NOT EXISTS``,
  comparisons with the ``IS`` operator (not ``=``) because some columns are nullable
  (``NULL = NULL`` is false in SQL → re-insertion → not idempotent; ``NULL IS NULL`` is
  true). Re-merging = no-op (each source row already has its exact twin).
- ``sources``, ``source_variants`` and ``source_observations`` as ``files``,
  ``observation_variants`` and ``observations`` (source points spec, D7).

The SQL lives in **Python constants** (consistent with ``catalog_repository.py``; no
new ``.sql`` for sqlfluff to lint). We NEVER write to the source (only SELECTs).
"""

import sqlite3
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path

from p2pwatch.adapters.persistence_sqlite.connection import open_catalog
from p2pwatch.adapters.persistence_sqlite.errors import PersistenceError
from p2pwatch.merge.errors import MergeError, SchemaVersionMismatchError

# Attach alias of the current source (one at a time → we stay at 1 attached DB
# whatever N, well under the SQLITE_MAX_ATTACHED cap of 10, spec §8).
_SRC = "src"

# --- Content-identity tables: INSERT OR IGNORE, explicit columns (no SELECT *). ---

_COPY_FILES = (
    f"INSERT OR IGNORE INTO main.files (file_id, network, native_id, size_bytes) "
    f"SELECT file_id, network, native_id, size_bytes FROM {_SRC}.files"
)


_VARIANT_COLUMNS = (
    "file_id, filename, size_bytes, duration_seconds, bitrate_kbps, raw_meta, keyword, node_id,"
    " content_hash"
)

_COPY_VARIANTS = (
    f"INSERT OR IGNORE INTO main.observation_variants ({_VARIANT_COLUMNS}) "
    f"SELECT {_VARIANT_COLUMNS} FROM {_SRC}.observation_variants ORDER BY variant_id"
)

_COPY_OBSERVATIONS = f"""
INSERT OR IGNORE INTO main.observations (variant_id, observed_at, source_count)
SELECT d.variant_id, o.observed_at, o.source_count
FROM {_SRC}.observations AS o
JOIN {_SRC}.observation_variants AS s ON s.variant_id = o.variant_id
JOIN main.observation_variants AS d ON d.content_hash = s.content_hash
"""

# DISTINCT drops the source's own twins, which NOT EXISTS against the destination cannot see.
_COPY_MATCH_DECISIONS = f"""
INSERT INTO main.match_decisions (file_id, target_id, rule_name, tier, decided_at, node_id)
SELECT DISTINCT file_id, target_id, rule_name, tier, decided_at, node_id
FROM {_SRC}.match_decisions AS s
WHERE NOT EXISTS (
    SELECT 1 FROM main.match_decisions AS d
    WHERE d.file_id IS s.file_id
      AND d.target_id IS s.target_id
      AND d.rule_name IS s.rule_name
      AND d.tier IS s.tier
      AND d.decided_at IS s.decided_at
      AND d.node_id IS s.node_id
)
"""

_COPY_SOURCES = (
    f"INSERT OR IGNORE INTO main.sources (source_id, network, native_id) "
    f"SELECT source_id, network, native_id FROM {_SRC}.sources"
)

_SOURCE_VARIANT_COLUMNS = (
    "file_id, source_id, name, software, role, contact_point, connectable, raw_meta,"
    " node_id, content_hash"
)

_COPY_SOURCE_VARIANTS = (
    f"INSERT OR IGNORE INTO main.source_variants ({_SOURCE_VARIANT_COLUMNS}) "
    f"SELECT {_SOURCE_VARIANT_COLUMNS} FROM {_SRC}.source_variants ORDER BY variant_id"
)

_COPY_SOURCE_OBSERVATIONS = f"""
INSERT OR IGNORE INTO main.source_observations (variant_id, observed_at, session_received_bytes)
SELECT d.variant_id, o.observed_at, o.session_received_bytes
FROM {_SRC}.source_observations AS o
JOIN {_SRC}.source_variants AS s ON s.variant_id = o.variant_id
JOIN main.source_variants AS d ON d.content_hash = s.content_hash
"""

# MANDATORY FK order (spec §4.3): the identities (files) BEFORE the journals that reference them.
_COPY_STATEMENTS = (
    _COPY_FILES,
    _COPY_VARIANTS,
    _COPY_OBSERVATIONS,
    _COPY_MATCH_DECISIONS,
    _COPY_SOURCES,
    _COPY_SOURCE_VARIANTS,
    _COPY_SOURCE_OBSERVATIONS,
)


def merge_catalogs(
    output: Path, source_catalogs: Sequence[Path], *, output_is_source_catalog: bool = False
) -> None:
    """Merges ``source_catalogs`` into ``output``, idempotent.

    ``output`` is opened via ``open_catalog``: a new file gets the schema + the triggers, an
    existing older catalog is first migrated in place, and the merge APPENDS (never a truncate).

    ``output_is_source_catalog`` (``--into`` mode): the output is itself one of the
    ``source_catalogs``; we do not re-attach to ourselves (idempotence guarantees we duplicate
    nothing there), so we skip the source catalog whose path resolves to ``output``.

    Any ``sqlite3.Error`` (corrupt source, incompatible schema, FK…), and ``open_catalog``'s
    ``PersistenceError`` on the output, is wrapped in ``MergeError``; ``ROLLBACK`` is best-effort.

    Before copying a source we check its ``PRAGMA user_version`` equals the current schema
    version (the one ``open_catalog`` just stamped on ``output``) and refuse any mismatch
    with a ``SchemaVersionMismatchError`` (a ``MergeError`` subtype). We never migrate a
    source in place, so an off-version schema could silently mis-copy.
    """
    try:
        connection = open_catalog(output)
    except PersistenceError as error:
        raise MergeError(f"cannot open output {output}: {error}") from error
    try:
        # The current schema version = whatever open_catalog stamped on the output; we read
        # it back rather than hardcode it, so this tracks the migration set automatically.
        expected_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        output_resolved = Path(output).resolve()
        for source_catalog in source_catalogs:
            if not (output_is_source_catalog and Path(source_catalog).resolve() == output_resolved):
                _merge_catalog(connection, source_catalog, expected_version)
    finally:
        connection.close()


def _merge_catalog(
    connection: sqlite3.Connection, source_catalog: Path, expected_version: int
) -> None:
    """Attaches ``source_catalog``, copies its tables in ONE transaction, detaches.

    ``ATTACH``/``DETACH`` are OUTSIDE a transaction (SQLite refuses to attach inside an
    open transaction). Right after the attach, BEFORE the ``BEGIN``, we reject any source
    whose schema version differs from ``expected_version`` (nothing is written yet; the
    ``finally`` still detaches). The copy is wrapped by ``BEGIN``/``COMMIT``; an error
    triggers a best-effort ``ROLLBACK`` then a best-effort ``DETACH``, and propagates as
    ``MergeError``: the output keeps no partial copy of this source.
    """
    try:
        # RESOLVED path (consistent with the --into skip that compares ``Path.resolve()``):
        # avoids a self-attach if the same DB is passed under two path forms.
        connection.execute(f"ATTACH DATABASE ? AS {_SRC}", (str(Path(source_catalog).resolve()),))
    except sqlite3.Error as error:
        raise MergeError(f"cannot attach source catalog {source_catalog}: {error}") from error
    try:
        source_version = int(connection.execute(f"PRAGMA {_SRC}.user_version").fetchone()[0])
        if source_version != expected_version:
            raise SchemaVersionMismatchError(
                f"source catalog {source_catalog} has schema version {source_version}, "
                f"expected {expected_version} (the current schema); merge refuses an "
                "out-of-version catalog (it never migrates a source catalog in place)"
            )
        connection.execute("BEGIN")
        try:
            for statement in _COPY_STATEMENTS:
                connection.execute(statement)
            connection.execute("COMMIT")
        except sqlite3.Error as error:
            with suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            raise MergeError(f"copy of {source_catalog} failed: {error}") from error
    finally:
        with suppress(sqlite3.Error):
            connection.execute(f"DETACH DATABASE {_SRC}")

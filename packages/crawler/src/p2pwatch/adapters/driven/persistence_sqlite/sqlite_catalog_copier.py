"""``CatalogCopier`` over SQLite: idempotent copy of N ``catalog.db`` into a single output.

A check pass first refuses a source at another schema version, or holding a value the node could
not read back (values-at-the-boundary spec, D9), before the output is opened: a refused merge
writes nothing.

Mechanism (merge spec §3/§4): the output is created/opened via ``open_catalog`` (the catalog
migrations, NO duplicated DDL). For each source: we ``ATTACH`` it (outside a transaction),
then INSIDE an explicit transaction (``BEGIN``…``COMMIT``, best-effort ``ROLLBACK`` on error)
we copy its tables in **FK order** (identities first), then ``COMMIT`` and ``DETACH``. A half-copied
source is never committed; a failed merge is re-run safely.

Idempotence (spec §4):
- ``files`` (global content PK) → ``INSERT OR IGNORE`` (first observation
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

The SQL lives in **Python constants** (consistent with ``sqlite_observation_store.py``; no
new ``.sql`` for sqlfluff to lint). We NEVER write to the source (only SELECTs).
"""

import json
import logging
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from pathlib import Path, PurePath

from catalog_matching.domain.validation import has_control_character
from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    SqliteDatabaseOpener,
)
from p2pwatch.application.ports.driven.catalog_copier import CatalogCopier
from p2pwatch.domain.catalog_copy_error import CatalogCopyError
from p2pwatch.domain.value_bounds import require_well_formed_text

_logger = logging.getLogger(__name__)

# Attach alias of the current source (one at a time → we stay at 1 attached DB
# whatever N, well under the SQLITE_MAX_ATTACHED cap of 10, spec §8).
_SRC = "src"

# --- Content-identity tables: INSERT OR IGNORE, explicit columns (no SELECT *). ---

_COPY_FILES = (
    f"INSERT OR IGNORE INTO main.files (file_id, network, native_id, size_bytes) "
    f"SELECT file_id, network, native_id, size_bytes FROM {_SRC}.files"
)


_VARIANT_COLUMNS = (
    "file_id, filename, size_bytes, duration_seconds, bitrate_kbps, raw_metadata, keyword, node_id,"
    " content_hash"
)

_COPY_VARIANTS = (
    f"INSERT OR IGNORE INTO main.observation_variants ({_VARIANT_COLUMNS}) "
    f"SELECT {_VARIANT_COLUMNS} FROM {_SRC}.observation_variants ORDER BY variant_id"
)

_COPY_OBSERVATIONS = f"""
INSERT OR IGNORE INTO main.observations (variant_id, observed_at_micros, source_count)
SELECT d.variant_id, o.observed_at_micros, o.source_count
FROM {_SRC}.observations AS o
JOIN {_SRC}.observation_variants AS s ON s.variant_id = o.variant_id
JOIN main.observation_variants AS d ON d.content_hash = s.content_hash
"""

# DISTINCT drops the source's own twins, which NOT EXISTS against the destination cannot see.
_COPY_MATCH_DECISIONS = f"""
INSERT INTO main.match_decisions (file_id, target_id, rule_name, tier, decided_at_micros, node_id)
SELECT DISTINCT file_id, target_id, rule_name, tier, decided_at_micros, node_id
FROM {_SRC}.match_decisions AS s
WHERE NOT EXISTS (
    SELECT 1 FROM main.match_decisions AS d
    WHERE d.file_id IS s.file_id
      AND d.target_id IS s.target_id
      AND d.rule_name IS s.rule_name
      AND d.tier IS s.tier
      AND d.decided_at_micros IS s.decided_at_micros
      AND d.node_id IS s.node_id
)
"""

_COPY_SOURCES = (
    f"INSERT OR IGNORE INTO main.sources (source_id, network, native_id) "
    f"SELECT source_id, network, native_id FROM {_SRC}.sources"
)

_SOURCE_VARIANT_COLUMNS = (
    "file_id, source_id, name, software, role, contact_point, connectable, raw_metadata,"
    " node_id, content_hash"
)

_COPY_SOURCE_VARIANTS = (
    f"INSERT OR IGNORE INTO main.source_variants ({_SOURCE_VARIANT_COLUMNS}) "
    f"SELECT {_SOURCE_VARIANT_COLUMNS} FROM {_SRC}.source_variants ORDER BY variant_id"
)

_COPY_SOURCE_OBSERVATIONS = f"""
INSERT OR IGNORE INTO main.source_observations
    (variant_id, observed_at_micros, session_received_bytes)
SELECT d.variant_id, o.observed_at_micros, o.session_received_bytes
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

# --- The check pass: SQL over the attached source, through the functions it registers. ---

# Every column declared TEXT, checked first: a function handed a text that is not UTF-8 fails
# before its body runs, so the content checks receive valid text only.
_SELECT_TEXT_COLUMNS = f"""
SELECT t.name AS table_name, c.name AS column_name
FROM {_SRC}.sqlite_schema AS t JOIN pragma_table_info(t.name, '{_SRC}') AS c
WHERE t.type = 'table' AND upper(c.type) = 'TEXT'
ORDER BY t.name, c.cid
"""

_SELECT_KEY_COLUMNS = f"SELECT name FROM pragma_table_info(?, '{_SRC}') WHERE pk > 0 ORDER BY pk"

_NOT_UTF8_WHERE = "NOT is_valid_utf8(CAST({column} AS BLOB))"
_NOT_PAIRS = "is not a JSON array of [name, value] pairs, or holds text that is not valid UTF-8"
_NOT_OBJECT = "is not a JSON object, or holds text that is not valid UTF-8"
_CONTROL = "holds a control character"

# (table, column, SQL true of a refused value of ``{column}``, what the refusal says of it)
_CONTENT_CHECKS = (
    ("observation_variants", "raw_metadata", "NOT is_metadata_pairs({column})", _NOT_PAIRS),
    ("source_variants", "raw_metadata", "NOT is_metadata_object({column})", _NOT_OBJECT),
    ("match_decisions", "target_id", "has_control_character({column})", _CONTROL),
    ("match_decisions", "rule_name", "has_control_character({column})", _CONTROL),
)


class SqliteCatalogCopier(CatalogCopier):
    """Checks every source, then copies each through ``ATTACH``, one transaction per source."""

    def __init__(self, database_opener: SqliteDatabaseOpener) -> None:
        self._database_opener = database_opener

    def copy_catalogs(self, destination: PurePath, *, source_catalogs: Sequence[PurePath]) -> None:
        _check_catalogs(self._database_opener, source_catalogs=source_catalogs)
        _copy_catalogs(
            self._database_opener, destination=Path(destination), source_catalogs=source_catalogs
        )


def _copy_catalogs(
    database_opener: SqliteDatabaseOpener, *, destination: Path, source_catalogs: Sequence[PurePath]
) -> None:
    """Copies ``source_catalogs`` into ``destination``, idempotent.

    ``destination`` is opened via ``open_catalog``: a new file gets the schema + the triggers, an
    existing older catalog is first migrated in place, and the copy APPENDS (never a truncate).

    Any ``sqlite3.Error`` (corrupt source, incompatible schema, FK…), and ``open_catalog``'s
    ``PersistenceError`` on the destination, is wrapped in ``CatalogCopyError``; ``ROLLBACK`` is
    best-effort.
    """
    try:
        connection = database_opener.open_catalog(destination)
    except PersistenceError as error:
        raise CatalogCopyError(f"cannot open output {destination}: {error}") from error
    try:
        for source_catalog in source_catalogs:
            _copy_catalog(connection, source_catalog=source_catalog)
            _logger.info("%s merged", source_catalog)
    finally:
        connection.close()


def _copy_catalog(connection: sqlite3.Connection, *, source_catalog: PurePath) -> None:
    """Attaches ``source_catalog``, copies its tables in ONE transaction, detaches.

    ``ATTACH``/``DETACH`` are OUTSIDE a transaction (SQLite refuses to attach inside an
    open transaction). The copy is wrapped by ``BEGIN``/``COMMIT``; an error
    triggers a best-effort ``ROLLBACK`` then a best-effort ``DETACH``, and propagates as
    ``CatalogCopyError``: the output keeps no partial copy of this source.
    """
    with _attached(connection, source_catalog=source_catalog):
        connection.execute("BEGIN")
        try:
            for statement in _COPY_STATEMENTS:
                connection.execute(statement)
            connection.execute("COMMIT")
        except sqlite3.Error as error:
            with suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            raise CatalogCopyError(f"copy of {source_catalog} failed: {error}") from error


def _check_catalogs(
    database_opener: SqliteDatabaseOpener, *, source_catalogs: Sequence[PurePath]
) -> None:
    """Checks each source attached to a database in memory, before the output is opened."""
    expected_version = database_opener.catalog_version()
    connection = database_opener.open_in_memory()
    connection.create_function("is_valid_utf8", 1, _is_valid_utf8, deterministic=True)
    connection.create_function("is_metadata_pairs", 1, _is_metadata_pairs, deterministic=True)
    connection.create_function("is_metadata_object", 1, _is_metadata_object, deterministic=True)
    connection.create_function(
        "has_control_character", 1, has_control_character, deterministic=True
    )
    try:
        for source_catalog in source_catalogs:
            with _attached(connection, source_catalog=source_catalog):
                _check_catalog(
                    connection, source_catalog=source_catalog, expected_version=expected_version
                )
    finally:
        connection.close()


def _check_catalog(
    connection: sqlite3.Connection, *, source_catalog: PurePath, expected_version: int
) -> None:
    """Refuses ``source_catalog`` at another schema version (a merge never migrates a source), or
    holding a value the node could not read back."""
    try:
        source_version = int(
            connection.execute(f"PRAGMA {_SRC}.user_version").fetchone()["user_version"]
        )
        if source_version != expected_version:
            raise CatalogCopyError(
                f"source catalog {source_catalog} has schema version {source_version}, "
                f"expected {expected_version} (the current schema); merge refuses an "
                "out-of-version catalog (it never migrates a source catalog in place)"
            )
        text_checks = [
            (row["table_name"], row["column_name"], _NOT_UTF8_WHERE, "is not valid UTF-8")
            for row in connection.execute(_SELECT_TEXT_COLUMNS)
        ]
        for table, column, refused_where, problem in (*text_checks, *_CONTENT_CHECKS):
            refused_row_key = _refused_row_key(
                connection, table=table, refused_where=refused_where.format(column=_quoted(column))
            )
            if refused_row_key is not None:
                raise CatalogCopyError(
                    f"source catalog {source_catalog} refused: {table}.{column} {problem},"
                    f" first at {refused_row_key}"
                )
    except sqlite3.Error as error:
        raise CatalogCopyError(f"cannot check source catalog {source_catalog}: {error}") from error


def _refused_row_key(
    connection: sqlite3.Connection, *, table: str, refused_where: str
) -> str | None:
    """The key of the first row of ``table`` where ``refused_where`` holds, else ``None``."""
    key_columns = [row["name"] for row in connection.execute(_SELECT_KEY_COLUMNS, (table,))]
    key_columns = key_columns or ["rowid"]
    keys = ", ".join(f"quote({_quoted(name)}) AS {_quoted(name)}" for name in key_columns)
    refused_row = connection.execute(
        f"SELECT {keys} FROM {_SRC}.{_quoted(table)} WHERE {refused_where} LIMIT 1"
    ).fetchone()
    if refused_row is None:
        return None
    return ", ".join(f"{name} {refused_row[name]}" for name in key_columns)


def _quoted(name: str) -> str:
    """``name`` as an SQL identifier, whatever it holds: the source names its own tables."""
    return '"' + name.replace('"', '""') + '"'


def _is_valid_utf8(encoded: bytes | None) -> bool:
    """Whether ``encoded`` decodes as UTF-8, strictly: it then holds no surrogate either."""
    try:
        (encoded or b"").decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _is_metadata_pairs(raw_metadata: str) -> bool:
    """Whether ``raw_metadata`` is what an observation's read unpacks: a JSON array of ``[name,
    value]`` pairs, each name a text, every text well formed."""
    decoded = _well_formed_json(raw_metadata)
    return isinstance(decoded, list) and all(
        isinstance(pair, list) and len(pair) == 2 and isinstance(pair[0], str) for pair in decoded
    )


def _is_metadata_object(raw_metadata: str) -> bool:
    """Whether ``raw_metadata`` is a JSON object, every text in it well formed."""
    return isinstance(_well_formed_json(raw_metadata), dict)


def _well_formed_json(text: str) -> object:
    """``text`` decoded as JSON, ``None`` unless it is JSON whose every text is well formed."""
    try:
        decoded = json.loads(text)
        # Dumped back as it came: every text of it, an object's keys included, reaches the check.
        require_well_formed_text(
            json.dumps(decoded, ensure_ascii=False), error_label="raw_metadata"
        )
    except ValueError:
        return None
    return decoded


@contextmanager
def _attached(connection: sqlite3.Connection, *, source_catalog: PurePath) -> Iterator[None]:
    """``source_catalog`` attached for the block, outside any transaction, detached best-effort."""
    try:
        connection.execute(f"ATTACH DATABASE ? AS {_SRC}", (str(Path(source_catalog).resolve()),))
    except sqlite3.Error as error:
        raise CatalogCopyError(f"cannot attach source catalog {source_catalog}: {error}") from error
    try:
        yield
    finally:
        with suppress(sqlite3.Error):
            connection.execute(f"DETACH DATABASE {_SRC}")

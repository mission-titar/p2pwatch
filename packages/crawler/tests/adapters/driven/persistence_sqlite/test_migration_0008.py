"""Catalog 0008 keys every table that names a file by ``file_id`` (stage 1, D1, D4 and D7)."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.variants import content_hash
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import Keyword, NodeId
from p2pwatch.domain.observation import FileObservation, ReportedFile
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.older_catalog import (
    open_catalog_at,
    open_catalog_forcing_secure_delete_at,
)
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_catalog

_A, _B = "a" * 32, "b" * 32
_ID_A, _ID_B = (
    FileKey(network=Network.ED2K, native_id=_A).file_id,
    FileKey(network=Network.ED2K, native_id=_B).file_id,
)
_VARIANTS = (
    (_A, "a.avi", 100, 1474, 1200, '[["codec", "xvid"]]', "keroro", "n1"),
    (_A, "a [VF].avi", 100, None, None, "[]", "titar", "n2"),
    (_B, "b.avi", 200, None, None, "[]", "keroro", "n1"),
)
_OBSERVATIONS = ((1, 10, 5), (1, 20, 6), (2, 10, 1), (3, 30, 2))
_DECISIONS = (
    (_A, "062A", "exact", "download", "2026-06-11T12:00:00.000000+00:00", "n1"),
    (_B, "062B", "loose", "notify", "2026-06-11T12:00:01.000000+00:00", "n1"),
    (_A, "062A", "", "retracted", "2026-06-11T12:00:02.000000+00:00", "n2"),
)
_ED2K_COLUMNS = """
SELECT m.name AS table_name, p.name AS column_name
FROM sqlite_schema AS m, pragma_table_info(m.name) AS p
WHERE m.type = 'table' AND (p.name LIKE '%ed2k%' OR p.name LIKE 'aich%')
"""
_VARIANT_COLUMNS = (
    "variant_id",
    "file_id",
    "filename",
    "size_bytes",
    "media_length_sec",
    "bitrate_kbps",
    "raw_meta",
    "keyword",
    "node_id",
    "content_hash",
)
_OBSERVATION_COLUMNS = ("variant_id", "observed_at", "source_count")
_DECISION_COLUMNS = ("id", "file_id", "target_id", "rule_name", "tier", "decided_at", "node_id")


def _catalog_at_7(path: Path) -> None:
    connection = open_catalog_at(path, version=7)
    for native_id, size in ((_A, 100), (_B, 200)):
        connection.execute(
            "INSERT INTO files (ed2k_hash, size_bytes) VALUES (?, ?)", (native_id, size)
        )
    for variant in _VARIANTS:
        connection.execute(
            "INSERT INTO observation_variants (ed2k_hash, filename, size_bytes, media_length_sec,"
            " bitrate_kbps, raw_meta, keyword, node_id, content_hash)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (*variant, content_hash(*variant)),
        )
    connection.executemany("INSERT INTO observations VALUES (?, ?, ?)", _OBSERVATIONS)
    connection.executemany(
        "INSERT INTO match_decisions (ed2k_hash, target_id, rule_name, tier, decided_at, node_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        _DECISIONS,
    )
    connection.close()


@pytest.fixture
def migrated(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    _catalog_at_7(tmp_path / "catalog.db")
    connection = open_catalog_at(tmp_path / "catalog.db", version=8)
    yield connection
    connection.close()


def test_files_are_keyed_by_the_file_id_of_their_network_and_native_id(
    migrated: sqlite3.Connection,
) -> None:
    assert rows(migrated, sql="PRAGMA user_version") == [{"user_version": 8}]
    assert rows(migrated, sql="SELECT * FROM files ORDER BY native_id") == [
        {"file_id": _ID_A, "network": "ed2k", "native_id": _A, "size_bytes": 100},
        {"file_id": _ID_B, "network": "ed2k", "native_id": _B, "size_bytes": 200},
    ]


def test_variants_keep_their_id_and_hash_the_file_id(migrated: sqlite3.Connection) -> None:
    file_ids = {_A: _ID_A, _B: _ID_B}
    expected = [
        dict(
            zip(
                _VARIANT_COLUMNS,
                (n, file_ids[v[0]], *v[1:], content_hash(file_ids[v[0]], *v[1:])),
                strict=True,
            )
        )
        for n, v in enumerate(_VARIANTS, start=1)
    ]
    assert rows(migrated, sql="SELECT * FROM observation_variants ORDER BY 1") == expected
    assert rows(migrated, sql="SELECT * FROM observations ORDER BY 1, 2") == [
        dict(zip(_OBSERVATION_COLUMNS, observation, strict=True)) for observation in _OBSERVATIONS
    ]


def test_decisions_keep_their_id_and_name_the_file_id(migrated: sqlite3.Connection) -> None:
    file_ids = {_A: _ID_A, _B: _ID_B}
    expected = [
        dict(zip(_DECISION_COLUMNS, (n, file_ids[d[0]], *d[1:]), strict=True))
        for n, d in enumerate(_DECISIONS, start=1)
    ]
    assert rows(migrated, sql="SELECT * FROM match_decisions ORDER BY id") == expected


def test_no_ed2k_identity_or_old_table_is_left(migrated: sqlite3.Connection) -> None:
    assert rows(migrated, sql=_ED2K_COLUMNS) == []
    tables = {row["name"] for row in rows(migrated, sql="SELECT name FROM sqlite_schema")}
    assert not {name for name in tables if name.endswith("_old")}
    indexes = rows(
        migrated,
        sql="SELECT name, tbl_name FROM sqlite_schema WHERE type = 'index' AND sql IS NOT NULL"
        " ORDER BY name",
    )
    # The index on file_id alone would be a prefix of the decision index: not carried.
    assert indexes == [
        {"name": "idx_match_decisions_file_target_decided", "tbl_name": "match_decisions"},
        {"name": "idx_observation_variants_file_id", "tbl_name": "observation_variants"},
    ]


def test_files_refuse_a_non_canonical_ed2k_id_or_an_unknown_network(
    migrated: sqlite3.Connection,
) -> None:
    for network, native_id in (("ed2k", _A.upper()), ("ed2k", "c" * 31), ("kad", "c" * 32)):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            migrated.execute(
                "INSERT INTO files VALUES (randomblob(16), ?, ?, 1)", (network, native_id)
            )


def test_a_new_observation_reuses_the_variant_0008_rekeyed(tmp_path: Path) -> None:
    """The store and 0008 hash a variant alike, or every file gets a second variant."""
    _catalog_at_7(tmp_path / "catalog.db")
    migrated = open_catalog(tmp_path / "catalog.db")  # the store writes today's columns
    reported_file = ReportedFile(
        file=FileKey(network=Network.ED2K, native_id=_B),
        filename="b.avi",
        size_bytes=200,
        source_count=4,
        keyword=Keyword("keroro"),
    )
    try:
        SqliteObservationStore(migrated).record_observation(
            FileObservation(
                reported_file=reported_file,
                observed_at=datetime(2026, 6, 12, tzinfo=UTC),
                node_id=NodeId("n1"),
            )
        )
        assert rows(migrated, sql="SELECT count(*) AS variant_count FROM observation_variants") == [
            {"variant_count": 3}
        ]
        assert rows(migrated, sql="SELECT count(*) AS observation_count FROM observations") == [
            {"observation_count": 5}
        ]
    finally:
        migrated.close()


def test_migrating_restores_the_pragmas_0008_sets(tmp_path: Path) -> None:
    _catalog_at_7(tmp_path / "catalog.db")
    connection = open_catalog_forcing_secure_delete_at(tmp_path / "catalog.db", version=8)
    try:
        assert rows(connection, sql="PRAGMA user_version") == [{"user_version": 8}]
        assert rows(connection, sql="PRAGMA secure_delete") == [{"secure_delete": 1}]
        assert rows(connection, sql="PRAGMA cache_size") == [{"cache_size": -2000}]
    finally:
        connection.close()

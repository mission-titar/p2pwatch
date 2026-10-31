"""``SqliteCatalogCopier``'s check pass: a source holding a value the node could not read back, or
a row inconsistent with its keys, is refused before the destination is opened, whether the merge
creates it or migrates it."""

import dataclasses
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord
from catalog_matching.domain.identifiers import TargetId
from p2pwatch.adapters.driven.persistence_sqlite.database_digest import database_digest
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_catalog_copier import SqliteCatalogCopier
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_source_point_store import (
    SqliteSourcePointStore,
)
from p2pwatch.domain.catalog_copy_error import CatalogCopyError
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.file_target_decision import DatedDecision
from p2pwatch.domain.identifiers import Keyword, NodeId
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.domain.source import SourceKey, SourcePoint, SourceReading, SourceRole
from tests.support.adapters.driven.persistence_sqlite.helpers import rows_without_id
from tests.support.adapters.driven.persistence_sqlite.older_catalog import open_catalog_at
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    database_opener,
    open_catalog,
    open_reader,
)

_FILE = FileKey(network=Network.ED2K, native_id="a" * 32)
_NODE_ID = NodeId("node-a")
_T0 = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
_NOT_UTF8 = "is not valid UTF-8"
_NOT_PAIRS = "is not a JSON array of [name, value] pairs, or holds text that is not valid UTF-8"
_NOT_OBJECT = "is not a JSON object, or holds text that is not valid UTF-8"
_CONTROL = "holds a control character"
_NOT_DERIVED = "is not the id its network and native_id derive"
_NOT_HASHED = "is not the hash of its variant's values"
_ZERO_ID = "zeroblob(16)"
# The key of the row ``_seed`` appends to a clean catalog.
_SEEDED_ROW_KEYS = {
    "files": "file_id X'00000000000000000000000000000000'",
    "sources": "source_id X'00000000000000000000000000000000'",
    "observation_variants": "variant_id 2",
    "source_variants": "variant_id 4",
    "match_decisions": "id 2",
}


def _copy_catalogs(destination: Path, *, source_catalogs: list[Path]) -> None:
    SqliteCatalogCopier(database_opener()).copy_catalogs(
        destination, source_catalogs=source_catalogs
    )


def _clean_catalog(path: Path) -> Path:
    """A catalog the stores wrote, its raw metadata holding texts, integers, a tuple and a null, its
    source variants connectable, not connectable and unknown."""
    reported_file = ReportedFile(
        file=_FILE,
        filename="Keroro mission Titar 062.avi",
        size_bytes=100,
        source_count=3,
        keyword=Keyword("keroro"),
        raw_metadata=(("codec", "xvid"), ("rating", 3), ("complete_source_count", None)),
    )
    decision = DecisionRecord(
        target_id=TargetId("062A"), rule_name="segment_id_loose", tier=DecisionTier.DOWNLOAD
    )
    reading = SourceReading(
        source=SourceKey(network=Network.ED2K, native_id="1f" * 16),
        source_name="AnimuseeFMR",
        software="eMule v0.50a",
        role=SourceRole.SENDING,
        contact_point=None,
        connectable=None,
        raw_metadata=(("ports", ("4662", "4672")), ("ecid", 7)),
        session_received_bytes=0,
    )
    points = [
        SourcePoint(
            file=_FILE,
            reading=dataclasses.replace(reading, connectable=connectable),
            role=SourceRole.SENDING,
            observed_at=_T0,
            node_id=_NODE_ID,
        )
        for connectable in (None, True, False)
    ]
    with closing(open_catalog(path)) as connection:
        SqliteObservationStore(connection).record_observation(
            FileObservation(reported_file=reported_file, observed_at=_T0, node_id=_NODE_ID)
        )
        SqliteDecisionStore(connection).record_decision(
            DatedDecision(file=_FILE, decision=decision, decided_at=_T0, node_id=_NODE_ID)
        )
        SqliteSourcePointStore(connection).record_points(points)
    return path


def _seed(catalog: Path, *, table: str, column: str, value_sql: str) -> None:
    """Appends to ``table`` a copy of its first row, ``column`` set to the SQL ``value_sql``."""
    # A fresh native_id and content_hash keep the copy clear of the UNIQUE constraints.
    replaced = {"native_id": f"'{'b' * 32}'", "content_hash": "randomblob(16)", column: value_sql}
    with closing(open_catalog(catalog)) as connection:
        columns = connection.execute(
            "SELECT name FROM pragma_table_info(?) WHERE pk = 0 OR name = ?", (table, column)
        )
        names = [row["name"] for row in columns]
        values = [replaced.get(name, name) for name in names]
        connection.execute(
            f"INSERT INTO {table} ({', '.join(names)})"
            f" SELECT {', '.join(values)} FROM {table} LIMIT 1"
        )


def _destination(directory: Path, *, into: bool) -> Path:
    """A catalog at schema version 5, which ``--into`` would migrate, or ``--output``'s new file."""
    directory.mkdir()
    if not into:
        return directory / "merged.db"
    path = directory / "catalog.db"
    open_catalog_at(path, version=5).close()
    return path


def _state(destination: Path) -> tuple[bytes | None, list[str]]:
    """``destination``'s digest if it exists, then the files beside it, the reader's included."""
    digest = None
    if destination.exists():
        with closing(open_reader(destination)) as reader:
            digest = database_digest(reader)
    return digest, sorted(path.name for path in destination.parent.iterdir())


@pytest.mark.parametrize("into", [False, True], ids=["output", "into"])
@pytest.mark.parametrize(
    ("table", "column", "value_sql", "problem"),
    [
        ("observation_variants", "filename", "CAST(x'4bff' AS TEXT)", _NOT_UTF8),
        ("observation_variants", "raw_metadata", r"""'[["a", "\ud800"]]'""", _NOT_PAIRS),
        ("observation_variants", "raw_metadata", "'not json'", _NOT_PAIRS),
        ("match_decisions", "target_id", "'062' || char(31) || 'A'", _CONTROL),
        ("match_decisions", "rule_name", "'segment' || char(9) || 'id'", _CONTROL),
        # Checked for UTF-8 first: a function handed such a text fails before its body runs.
        ("observation_variants", "raw_metadata", "CAST(x'5bff' AS TEXT)", _NOT_UTF8),
        ("source_variants", "name", "CAST(x'ff' AS TEXT)", _NOT_UTF8),
        ("observation_variants", "raw_metadata", "'{}'", _NOT_PAIRS),
        ("observation_variants", "raw_metadata", """'["ab"]'""", _NOT_PAIRS),
        ("observation_variants", "raw_metadata", """'[["a"]]'""", _NOT_PAIRS),
        ("observation_variants", "raw_metadata", """'[[1, "a"]]'""", _NOT_PAIRS),
        ("source_variants", "raw_metadata", "'[]'", _NOT_OBJECT),
        ("source_variants", "raw_metadata", r"""'{"\udc80": 1}'""", _NOT_OBJECT),
        ("source_variants", "raw_metadata", r"""'{"a": ["b", "\ud800"]}'""", _NOT_OBJECT),
        ("files", "file_id", _ZERO_ID, _NOT_DERIVED),
        ("sources", "source_id", _ZERO_ID, _NOT_DERIVED),
        ("observation_variants", "content_hash", "randomblob(16)", _NOT_HASHED),
        ("source_variants", "content_hash", "randomblob(16)", _NOT_HASHED),
    ],
)
def test_a_source_holding_a_value_the_node_cannot_read_leaves_the_destination_as_it_was(
    *, tmp_path: Path, into: bool, table: str, column: str, value_sql: str, problem: str
) -> None:
    source = _clean_catalog(tmp_path / "source.db")
    _seed(source, table=table, column=column, value_sql=value_sql)
    destination = _destination(tmp_path / "destination", into=into)
    before = _state(destination)

    with pytest.raises(CatalogCopyError) as raised:
        _copy_catalogs(destination, source_catalogs=[source])

    expected = f"source catalog {source} refused: {table}.{column} {problem}, first at"
    assert str(raised.value) == f"{expected} {_SEEDED_ROW_KEYS[table]}"
    assert _state(destination) == before


def test_a_text_column_of_a_table_the_schema_does_not_hold_is_checked_too(tmp_path: Path) -> None:
    source = _clean_catalog(tmp_path / "source.db")
    with closing(open_catalog(source)) as connection:
        connection.execute('CREATE TABLE "no""tes" (body TEXT)')
        connection.execute("""INSERT INTO "no""tes" (body) VALUES (CAST(x'ff' AS TEXT))""")

    with pytest.raises(CatalogCopyError) as raised:
        _copy_catalogs(tmp_path / "merged.db", source_catalogs=[source])

    expected = f'source catalog {source} refused: no"tes.body {_NOT_UTF8}, first at rowid 1'
    assert str(raised.value) == expected


def test_a_source_native_id_its_network_refuses_is_named(tmp_path: Path) -> None:
    source = _clean_catalog(tmp_path / "source.db")
    with closing(open_catalog(source)) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute("INSERT INTO sources VALUES (zeroblob(16), 'ed2k', 'not a user hash')")

    with pytest.raises(CatalogCopyError) as raised:
        _copy_catalogs(tmp_path / "merged.db", source_catalogs=[source])

    expected = f"source catalog {source} refused: sources.source_id {_NOT_DERIVED}, first at"
    assert str(raised.value) == f"{expected} {_SEEDED_ROW_KEYS['sources']}"


def test_a_source_missing_a_table_cannot_be_checked(tmp_path: Path) -> None:
    source = _clean_catalog(tmp_path / "source.db")
    with closing(open_catalog(source)) as connection:
        connection.execute("DROP TABLE match_decisions")

    with pytest.raises(CatalogCopyError) as raised:
        _copy_catalogs(tmp_path / "merged.db", source_catalogs=[source])

    assert str(raised.value) == (
        f"cannot check source catalog {source}: no such table: src.match_decisions"
    )
    assert not (tmp_path / "merged.db").exists()


def test_a_source_the_stores_wrote_merges_whole(tmp_path: Path) -> None:
    source = _clean_catalog(tmp_path / "source.db")
    destination = tmp_path / "merged.db"

    _copy_catalogs(destination, source_catalogs=[source])

    for table in ("observations", "match_decisions", "source_variants", "source_observations"):
        assert rows_without_id(destination, table=table) == rows_without_id(source, table=table)

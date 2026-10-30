"""``SqliteCatalogCopier``: ATTACH + idempotent INSERT…SELECT, merge design §7.

Everything is tested without Docker: we build N real ``catalog.db`` files (helpers), merge,
and assert content + cardinality + reassigned ``id`` + idempotence.
"""

import sqlite3
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_catalog_copier import SqliteCatalogCopier
from p2pwatch.domain.catalog_copy_error import CatalogCopyError
from p2pwatch.domain.file_key import FileKey, Network
from tests.support.adapters.driven.persistence_sqlite.helpers import (
    HASH_A,
    HASH_B,
    count,
    hash_for,
    make_catalog,
    rows_without_id,
    sorted_by_values,
    stamp_user_version,
    variant_ids,
)
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    database_opener,
    open_catalog,
)

# The current catalog schema version = the last catalog migration's number.
# open_catalog stamps the output to it; the guard rejects any source that is not at it.
_CURRENT_SCHEMA_VERSION = 15
_T1 = "2026-06-11T12:00:00.000000+00:00"
_T2 = "2026-06-11T13:00:00.000000+00:00"
_COPIER_LOGGER = "p2pwatch.adapters.driven.persistence_sqlite.sqlite_catalog_copier"


def _copy_catalogs(destination: Path, source_catalogs: list[Path]) -> None:
    SqliteCatalogCopier(database_opener()).copy_catalogs(
        destination, source_catalogs=source_catalogs
    )


def _file_observation(native_id: str, *, node_id: str, observed_at: str) -> dict[str, object]:
    """An observation with no media metadata (its nullable columns left NULL)."""
    return {
        "native_id": native_id,
        "filename": "keroro.avi",
        "source_count": 3,
        "observed_at": observed_at,
        "node_id": node_id,
    }


def _full_catalog(letter: str, *, node_id: str) -> dict[str, list[dict[str, object]]]:
    """A consistent catalog: 1 file, 1 row in each of the 2 journals, 1 source point."""
    ed2k = hash_for(letter)
    return {
        "files": [{"native_id": ed2k, "size_bytes": 100}],
        "observations": [_file_observation(ed2k, node_id=node_id, observed_at=_T1)],
        "match_decisions": [
            {
                "native_id": ed2k,
                "target_id": "062A",
                "rule_name": "r",
                "tier": "download",
                "decided_at": _T1,
                "node_id": node_id,
            }
        ],
        "source_observations": [
            {"native_id": ed2k, "user_hash": ed2k, "node_id": node_id, "observed_at_micros": 10}
        ],
    }


_ALL_TABLES = (
    "files",
    "observations",
    "match_decisions",
    "sources",
    "source_variants",
    "source_observations",
)
_SOURCE_TABLES = ("sources", "source_variants", "source_observations")


def _source_points(
    *moments: int, user_hash: str | None = HASH_B
) -> dict[str, list[dict[str, object]]]:
    """One source on one file, one variant, a point per moment; its counter grows with time."""
    return {
        "files": [{"native_id": HASH_A, "size_bytes": 100}],
        "source_observations": [
            {
                "native_id": HASH_A,
                "user_hash": user_hash,
                "node_id": "n1",
                "observed_at_micros": moment,
                "session_received_bytes": moment,
            }
            for moment in moments
        ],
    }


def test_t1_merge_two_distinct_catalogs(tmp_path: Path) -> None:
    src_a = make_catalog(tmp_path / "a.db", content=_full_catalog("a", node_id="node-a"))
    src_b = make_catalog(tmp_path / "b.db", content=_full_catalog("b", node_id="node-b"))
    src_c = make_catalog(tmp_path / "c.db", content=_full_catalog("c", node_id="node-c"))
    destination = tmp_path / "out.db"

    # N=3 also proves we attach one source at a time (never > 1 attached DB).
    _copy_catalogs(destination, [src_a, src_b, src_c])

    # Each table's cardinality = sum (disjoint contents); FKs satisfied (otherwise the
    # COMMIT would have raised). All rows from the 3 sources are present in the output.
    for table in _ALL_TABLES:
        assert count(destination, table=table) == 3
        expected = sorted_by_values(
            rows_without_id(src_a, table=table)
            + rows_without_id(src_b, table=table)
            + rows_without_id(src_c, table=table)
        )
        assert rows_without_id(destination, table=table) == expected


def test_t2_merge_overlapping_identity_files_or_ignore(tmp_path: Path) -> None:
    # Both sources share the SAME native_id (content-identity).
    src_a = make_catalog(
        tmp_path / "a.db", content={"files": [{"native_id": HASH_A, "size_bytes": 100}]}
    )
    src_b = make_catalog(
        tmp_path / "b.db", content={"files": [{"native_id": HASH_A, "size_bytes": 100}]}
    )
    destination = tmp_path / "out.db"

    _copy_catalogs(destination, [src_a, src_b])

    # INSERT OR IGNORE: the already-present PK is ignored → a single row.
    assert count(destination, table="files") == 1


def test_t3_re_merge_is_idempotent(tmp_path: Path) -> None:
    src_a = make_catalog(tmp_path / "a.db", content=_full_catalog("a", node_id="node-a"))
    src_b = make_catalog(tmp_path / "b.db", content=_full_catalog("b", node_id="node-b"))
    destination = tmp_path / "out.db"

    _copy_catalogs(destination, [src_a, src_b])
    first_pass = {table: rows_without_id(destination, table=table) for table in _ALL_TABLES}

    # Re-merge same sources into same output → WHERE NOT EXISTS false everywhere → no-op.
    _copy_catalogs(destination, [src_a, src_b])

    for table in _ALL_TABLES:
        assert rows_without_id(destination, table=table) == first_pass[table]


def test_t4_journal_dedup_identical_rows_including_nulls(tmp_path: Path) -> None:
    # BIT-FOR-BIT identical observation (same NULLs on duration_seconds and bitrate_kbps).
    obs = _file_observation(HASH_A, node_id="node", observed_at=_T1)
    src_a = make_catalog(
        tmp_path / "a.db",
        content={"files": [{"native_id": HASH_A, "size_bytes": 100}], "observations": [obs]},
    )
    src_b = make_catalog(
        tmp_path / "b.db",
        content={"files": [{"native_id": HASH_A, "size_bytes": 100}], "observations": [obs]},
    )
    destination = tmp_path / "out.db"

    _copy_catalogs(destination, [src_a, src_b])

    # The variant is found by its content_hash, NULLs included, and the observation by its key.
    assert count(destination, table="observation_variants") == 1
    assert count(destination, table="observations") == 1


def test_t4_journal_distinct_observed_at_keeps_both(tmp_path: Path) -> None:
    # Same file, same node, two INSTANTS → two REAL observations, distinct natural keys
    # → both kept (non-destructive).
    src_a = make_catalog(
        tmp_path / "a.db",
        content={
            "files": [{"native_id": HASH_A, "size_bytes": 100}],
            "observations": [_file_observation(HASH_A, node_id="node", observed_at=_T1)],
        },
    )
    src_b = make_catalog(
        tmp_path / "b.db",
        content={
            "files": [{"native_id": HASH_A, "size_bytes": 100}],
            "observations": [_file_observation(HASH_A, node_id="node", observed_at=_T2)],
        },
    )
    destination = tmp_path / "out.db"

    _copy_catalogs(destination, [src_a, src_b])

    assert count(destination, table="observation_variants") == 1
    assert count(destination, table="observations") == 2


def _decided(decided_at: str) -> dict[str, list[dict[str, object]]]:
    """A catalog of one file and one decision on it, made at ``decided_at``."""
    return {
        "files": [{"native_id": HASH_A, "size_bytes": 100}],
        "match_decisions": [
            {
                "native_id": HASH_A,
                "target_id": "062A",
                "rule_name": "r",
                "tier": "download",
                "decided_at": decided_at,
                "node_id": "node",
            }
        ],
    }


def test_twin_decisions_in_one_source_merge_as_one(tmp_path: Path) -> None:
    twins = _decided(_T1)
    twins["match_decisions"] *= 2
    src = make_catalog(tmp_path / "a.db", content=twins)
    destination = tmp_path / "out.db"

    _copy_catalogs(destination, [src])

    assert count(src, table="match_decisions") == 2
    assert count(destination, table="match_decisions") == 1


def test_a_decision_differing_only_by_its_decided_at_is_kept(tmp_path: Path) -> None:
    src_a = make_catalog(tmp_path / "a.db", content=_decided(_T1))
    src_b = make_catalog(tmp_path / "b.db", content=_decided(_T2))
    destination = tmp_path / "out.db"

    _copy_catalogs(destination, [src_a, src_b])

    assert count(destination, table="match_decisions") == 2


def test_t5_variant_ids_are_reassigned(tmp_path: Path) -> None:
    # Each source has a DISTINCT variant that (by autoincrement) carries variant_id=1.
    src_a = make_catalog(
        tmp_path / "a.db",
        content={
            "files": [{"native_id": HASH_A, "size_bytes": 100}],
            "observations": [_file_observation(HASH_A, node_id="node-a", observed_at=_T1)],
        },
    )
    src_b = make_catalog(
        tmp_path / "b.db",
        content={
            "files": [{"native_id": HASH_B, "size_bytes": 200}],
            "observations": [_file_observation(HASH_B, node_id="node-b", observed_at=_T2)],
        },
    )
    assert variant_ids(src_a) == variant_ids(src_b) == [1]
    destination = tmp_path / "out.db"

    _copy_catalogs(destination, [src_a, src_b])

    # The output numbers its own variants, and each observation follows its variant.
    assert variant_ids(destination) == [1, 2]
    expected = rows_without_id(src_a, table="observations") + rows_without_id(
        src_b, table="observations"
    )
    assert rows_without_id(destination, table="observations") == sorted_by_values(expected)


def test_t6_fk_order_inserts_identity_first(tmp_path: Path) -> None:
    # A source whose journals reference files. If the insertion order were reversed
    # (journals before identities), the FK would raise; the merge succeeds so the order holds.
    src = make_catalog(tmp_path / "a.db", content=_full_catalog("a", node_id="node-a"))
    destination = tmp_path / "out.db"

    _copy_catalogs(destination, [src])

    assert count(destination, table="observations") == 1
    assert count(destination, table="match_decisions") == 1


def test_t14_files_first_sight_wins(tmp_path: Path) -> None:
    # The same file with two sizes: the first source merged keeps its row (§6 rule frozen).
    src_a = make_catalog(
        tmp_path / "a.db", content={"files": [{"native_id": HASH_A, "size_bytes": 100}]}
    )
    src_b = make_catalog(
        tmp_path / "b.db", content={"files": [{"native_id": HASH_A, "size_bytes": 200}]}
    )
    destination = tmp_path / "out.db"

    _copy_catalogs(destination, [src_b, src_a])

    assert rows_without_id(destination, table="files") == [{"native_id": HASH_A, "size_bytes": 200}]


def test_t15_append_only_triggers_present_on_output(tmp_path: Path) -> None:
    src = make_catalog(
        tmp_path / "a.db", content={"files": [{"native_id": HASH_A, "size_bytes": 100}]}
    )
    destination = tmp_path / "out.db"
    _copy_catalogs(destination, [src])

    connection = open_catalog(destination)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="files is append-only"):
            connection.execute("UPDATE files SET size_bytes = 2")
        with pytest.raises(sqlite3.IntegrityError, match="files is append-only"):
            connection.execute("DELETE FROM files")
    finally:
        connection.close()


def test_t16_merger_wraps_source_copy_in_a_transaction(tmp_path: Path) -> None:
    # A source with a broken schema (empty SQLite DB, no tables) → the copy fails
    # midway → ROLLBACK: the output keeps NO partial copy of this source.
    good = make_catalog(tmp_path / "good.db", content=_full_catalog("a", node_id="node-a"))

    broken = tmp_path / "broken.db"
    raw = sqlite3.connect(broken)
    raw.execute("PRAGMA journal_mode=WAL")
    raw.execute("CREATE TABLE files (file_id BLOB, network TEXT, native_id TEXT, size_bytes INT)")
    raw.execute(
        "INSERT INTO files VALUES (?, 'ed2k', ?, 200)",
        (FileKey(network=Network.ED2K, native_id=HASH_B).file_id, HASH_B),
    )
    raw.commit()
    raw.close()
    # Stamp the current schema version so this source clears the version guard and reaches
    # the copy: we are exercising the mid-copy ROLLBACK, not the version rejection.
    stamp_user_version(broken, version=_CURRENT_SCHEMA_VERSION)

    destination = tmp_path / "out.db"
    _copy_catalogs(destination, [good])  # the good source first, in its own successful merge.

    with pytest.raises(CatalogCopyError, match="copy of .* failed"):
        _copy_catalogs(destination, [broken])

    # files (1st table) may have been copied BEFORE the failure on observation_variants (missing
    # table); the ROLLBACK must have undone it → the output still has ONLY the content of `good`.
    assert rows_without_id(destination, table="files") == [{"native_id": HASH_A, "size_bytes": 100}]


def test_t16_unattachable_source_errors(tmp_path: Path) -> None:
    # A source that is NOT a SQLite database (file exists but header invalid) →
    # the ATTACH itself raises → clear CatalogCopyError (attach branch, distinct from the copy).
    not_a_db = tmp_path / "garbage.db"
    not_a_db.write_bytes(b"not a sqlite database header" * 8)
    destination = tmp_path / "out.db"

    with pytest.raises(CatalogCopyError, match="cannot attach source catalog"):
        _copy_catalogs(destination, [not_a_db])


def test_t17_single_source_merge(tmp_path: Path) -> None:
    src = make_catalog(tmp_path / "a.db", content=_full_catalog("a", node_id="node-a"))
    destination = tmp_path / "out.db"

    _copy_catalogs(destination, [src])

    for table in _ALL_TABLES:
        assert rows_without_id(destination, table=table) == rows_without_id(src, table=table)


def test_each_source_copied_says_so(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    src_a = make_catalog(tmp_path / "a.db", content=_full_catalog("a", node_id="node-a"))
    src_b = make_catalog(tmp_path / "b.db", content=_full_catalog("b", node_id="node-b"))
    caplog.set_level("INFO", logger=_COPIER_LOGGER)

    _copy_catalogs(tmp_path / "out.db", [src_a, src_b])

    copier_messages = [r.getMessage() for r in caplog.records if r.name == _COPIER_LOGGER]
    assert copier_messages == [f"{src_a} merged", f"{src_b} merged"]


def test_rejects_source_with_older_schema_version(tmp_path: Path) -> None:
    # A source stamped to an OLDER schema (e.g. a 0001/0002-era DB) is refused BEFORE any
    # row is copied: the merge never migrates a source in place, so an off-version schema
    # could silently mis-copy. Fail-fast with the source path + both versions in the message.
    src = make_catalog(tmp_path / "old.db", content=_full_catalog("a", node_id="node-a"))
    stamp_user_version(src, version=_CURRENT_SCHEMA_VERSION - 1)
    destination = tmp_path / "out.db"

    with pytest.raises(CatalogCopyError) as excinfo:
        _copy_catalogs(destination, [src])

    message = str(excinfo.value)
    assert f"source catalog {src} has schema version" in message
    assert str(_CURRENT_SCHEMA_VERSION - 1) in message
    assert str(_CURRENT_SCHEMA_VERSION) in message
    # Rejected before its BEGIN: no row of the source reached the output.
    assert count(destination, table="files") == 0


def test_rejects_source_with_newer_schema_version(tmp_path: Path) -> None:
    # Strict equality: a NEWER source (a future 0004 schema the code does not know) is
    # refused too, consistent with open_catalog refusing a DB newer than the code.
    src = make_catalog(tmp_path / "new.db", content=_full_catalog("a", node_id="node-a"))
    stamp_user_version(src, version=_CURRENT_SCHEMA_VERSION + 1)
    destination = tmp_path / "out.db"

    with pytest.raises(CatalogCopyError, match="has schema version"):
        _copy_catalogs(destination, [src])

    assert count(destination, table="files") == 0


def test_source_at_current_schema_version_still_merges(tmp_path: Path) -> None:
    # Happy path: a source at the current schema version passes the guard and merges.
    # (make_catalog stamps the current version; the explicit stamp documents the intent.)
    src = make_catalog(tmp_path / "a.db", content=_full_catalog("a", node_id="node-a"))
    stamp_user_version(src, version=_CURRENT_SCHEMA_VERSION)
    destination = tmp_path / "out.db"

    _copy_catalogs(destination, [src])

    assert count(destination, table="files") == 1


def test_guard_checks_every_source_not_just_the_first(tmp_path: Path) -> None:
    # A valid first source then an off-version second: the guard runs per source, so the
    # second is rejected. The first was committed in its own transaction and survives.
    good = make_catalog(tmp_path / "good.db", content=_full_catalog("a", node_id="node-a"))
    bad = make_catalog(tmp_path / "bad.db", content=_full_catalog("b", node_id="node-b"))
    stamp_user_version(bad, version=_CURRENT_SCHEMA_VERSION - 1)
    destination = tmp_path / "out.db"

    with pytest.raises(CatalogCopyError, match=f"{bad} has schema version"):
        _copy_catalogs(destination, [good, bad])

    # The good source merged first (own transaction, committed); only its row is present.
    assert count(destination, table="files") == 1
    assert rows_without_id(destination, table="files") == [
        {"native_id": hash_for("a"), "size_bytes": 100}
    ]


def test_an_output_open_catalog_refuses_raises_a_merge_error(tmp_path: Path) -> None:
    # The use case maps only CatalogCopyError: a MigrationError would be a bare traceback.
    src = make_catalog(tmp_path / "a.db", content=_full_catalog("a", node_id="node-a"))
    destination = make_catalog(tmp_path / "out.db", content={})
    stamp_user_version(destination, version=_CURRENT_SCHEMA_VERSION + 1)

    with pytest.raises(CatalogCopyError, match=f"cannot open output {destination}"):
        _copy_catalogs(destination, [src])


@pytest.mark.parametrize("user_hash", [HASH_B, None])
@pytest.mark.parametrize("first_first", [True, False])
def test_two_catalogs_sharing_a_variant_merge_into_the_union_of_their_points(
    tmp_path: Path, user_hash: str | None, first_first: bool
) -> None:
    first = make_catalog(tmp_path / "first.db", content=_source_points(10, 20, user_hash=user_hash))
    second = make_catalog(
        tmp_path / "second.db", content=_source_points(20, 30, user_hash=user_hash)
    )
    union = make_catalog(
        tmp_path / "union.db", content=_source_points(10, 20, 30, user_hash=user_hash)
    )
    destination = tmp_path / "out.db"

    _copy_catalogs(destination, [first, second] if first_first else [second, first])

    merged = {table: rows_without_id(destination, table=table) for table in _SOURCE_TABLES}
    assert merged == {table: rows_without_id(union, table=table) for table in _SOURCE_TABLES}
    _copy_catalogs(destination, [first])
    _copy_catalogs(destination, [second])
    assert {table: rows_without_id(destination, table=table) for table in _SOURCE_TABLES} == merged


def test_a_copy_diverged_from_a_restored_catalog_merges_into_the_union(tmp_path: Path) -> None:
    # Stage 4 refused it whole: a range could not grow past one opened after the restore.
    restored = make_catalog(tmp_path / "restored.db", content=_source_points(10, 20, 100, 130))
    copy = make_catalog(tmp_path / "copy.db", content=_source_points(10, 50, 60, 70))
    union = make_catalog(
        tmp_path / "union.db", content=_source_points(10, 20, 50, 60, 70, 100, 130)
    )
    destination = tmp_path / "out.db"

    _copy_catalogs(destination, [restored, copy])

    observations = rows_without_id(destination, table="source_observations")
    assert observations == rows_without_id(union, table="source_observations")

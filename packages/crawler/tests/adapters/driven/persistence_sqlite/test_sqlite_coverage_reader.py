"""TDD tests for the catalog's coverage reader (spec W-D6 / §6)."""

import sqlite3
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_coverage_reader import SqliteCoverageReader
from p2pwatch.adapters.driven.persistence_sqlite.thread_read_connections import (
    ThreadReadConnections,
)
from tests.support.catalog_rows import insert_decision, insert_file
from tests.support.catalog_seeds import seed, seed_retracted, seed_whole_episode

# ---------------------------------------------------------------------------
# Tests: coverage
# ---------------------------------------------------------------------------


def _read_target_coverage(catalog_db: Path) -> Mapping[str, tuple[str, ...]]:
    with ThreadReadConnections(catalog_db) as thread_read_connections:
        return SqliteCoverageReader(thread_read_connections).read_target_coverage()


def test_target_coverage_groups_by_target(catalog_db: Path) -> None:
    seed(catalog_db)
    coverage = _read_target_coverage(catalog_db)
    assert coverage["062A"] == ("download",)


def test_target_coverage_empty_db_returns_empty(catalog_db: Path) -> None:
    coverage = _read_target_coverage(catalog_db)
    assert coverage == {}


def test_target_coverage_multiple_files_same_target(catalog_db: Path) -> None:
    """Two files matching the same target_id → two tiers."""
    with closing(sqlite3.connect(catalog_db)) as connection, connection:
        for suffix in ("a", "b"):
            insert_file(connection, suffix * 32)
            insert_decision(connection, suffix * 32, "062A", "download")
    coverage = _read_target_coverage(catalog_db)
    assert len(coverage["062A"]) == 2


def test_target_coverage_whole_episode_contributes_to_both_targets(catalog_db: Path) -> None:
    seed_whole_episode(catalog_db)
    coverage = _read_target_coverage(catalog_db)
    assert coverage["072A"] == ("download",)
    assert coverage["072B"] == ("download",)


def test_target_coverage_ignores_legacy_empty_target_sentinel(catalog_db: Path) -> None:
    h = "e" * 32
    with closing(sqlite3.connect(catalog_db)) as connection, connection:
        insert_file(connection, h)
        insert_decision(
            connection,
            h,
            "090A",
            "download",
            rule_name="id_segment_exact",
            decided_at="2026-07-05T10:00:00.000000+00:00",
        )
        insert_decision(
            connection,
            h,
            "",
            "retracted",
            rule_name="",
            decided_at="2026-07-05T11:00:00.000000+00:00",
        )
    coverage = _read_target_coverage(catalog_db)
    assert coverage["090A"] == ("download",)
    assert "" not in coverage


# ---------------------------------------------------------------------------
# Tests: "latest per hash", tie-break on decided_at then id
# ---------------------------------------------------------------------------


def test_target_coverage_uses_latest_decision_per_hash(catalog_db: Path) -> None:
    """Same hash with two decisions (T1 < T2) → the coverage reads T2's tier."""
    h = "a" * 32
    with closing(sqlite3.connect(catalog_db)) as connection, connection:
        insert_file(connection, h)
        insert_decision(connection, h, "062A", "catalog")
        insert_decision(
            connection, h, "062A", "download", decided_at="2026-06-22T11:00:00.000000+00:00"
        )
    coverage = _read_target_coverage(catalog_db)
    assert coverage["062A"] == ("download",)


def test_target_coverage_omits_retracted(catalog_db: Path) -> None:
    """A file whose latest decision is a retraction contributes to NO target's coverage."""
    seed(catalog_db)
    seed_retracted(catalog_db)
    coverage = _read_target_coverage(catalog_db)
    assert coverage["062A"] == ("download",)
    assert "063A" not in coverage  # the retracted file's earlier (now stale) target


def test_coverage_tie_break_on_id(catalog_db: Path) -> None:
    """Same hash, same decided_at, two different tiers → the larger id wins."""
    h = "b" * 32
    with closing(sqlite3.connect(catalog_db)) as connection, connection:
        insert_file(connection, h, 200)
        insert_decision(connection, h, "062A", "catalog")
        insert_decision(connection, h, "062A", "download")
    coverage = _read_target_coverage(catalog_db)
    assert coverage["062A"] == ("download",)

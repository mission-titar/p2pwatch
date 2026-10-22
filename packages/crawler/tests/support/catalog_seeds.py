"""The catalogs the readers' tests seed: a matched file, a whole episode, a retracted one."""

import sqlite3
from contextlib import closing
from pathlib import Path

from tests.support.catalog_rows import insert_decision, insert_file, insert_observation


def seed(db: Path) -> None:
    """Populate the database with a file, an observation, a decision."""
    with closing(sqlite3.connect(db)) as conn, conn:
        insert_file(conn, "a" * 32)
        insert_observation(conn, "a" * 32, "keroro_062.avi", source_count=5)
        insert_decision(
            conn,
            "a" * 32,
            "062A",
            "download",
            rule_name="id_segment_exact",
            decided_at="2026-06-22T10:00:01.000000+00:00",
        )


def seed_whole_episode(db: Path) -> None:
    """A single whole-episode file (hash a*32) satisfying BOTH segments 072A + 072B (two
    current decisions at tier ``download``): the core multi-target fixture (spec §9).
    Standalone: never combine with ``seed`` (same hash)."""
    h = "a" * 32
    with closing(sqlite3.connect(db)) as conn, conn:
        insert_file(conn, h, 170_000_000)
        insert_observation(
            conn,
            h,
            "keroro_072.avi",
            observed_at="2026-07-01T10:00:00.000000+00:00",
            size_bytes=170_000_000,
            source_count=7,
        )
        for tid in ("072A", "072B"):
            insert_decision(
                conn,
                h,
                tid,
                "download",
                rule_name="numero_nu_confirmed",
                decided_at="2026-07-01T10:00:01.000000+00:00",
            )


def seed_retracted(db: Path) -> None:
    """Add a third file (c*32) that WAS matched (063A) then had that target retracted
    per-target: a ``(hash, 063A, tier="retracted")`` marker appended after the real decision
    (the new per-target retraction model, spec §6). Its latest 063A row is a retraction, so
    it must be treated as unmatched everywhere."""
    h = "c" * 32
    with closing(sqlite3.connect(db)) as conn, conn:
        insert_file(conn, h, 300)
        insert_observation(
            conn,
            h,
            "keroro_063.avi",
            observed_at="2026-06-22T09:00:00.000000+00:00",
            size_bytes=300,
            source_count=2,
        )
        insert_decision(conn, h, "063A", "download", rule_name="id_segment_exact")
        insert_decision(
            conn,
            h,
            "063A",
            "retracted",
            rule_name="",
            decided_at="2026-06-22T11:00:00.000000+00:00",
        )

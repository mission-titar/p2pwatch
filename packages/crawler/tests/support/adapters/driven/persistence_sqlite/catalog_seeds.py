"""The catalog the readers' tests seed: a matched file."""

import sqlite3
from contextlib import closing
from pathlib import Path

from tests.support.catalog_rows import insert_decision, insert_file, insert_observation


def seed(db: Path) -> None:
    """Populate the database with a file, an observation, a decision."""
    with closing(sqlite3.connect(db)) as connection, connection:
        insert_file(connection, native_id="a" * 32)
        insert_observation(
            connection, native_id="a" * 32, filename="keroro_062.avi", source_count=5
        )
        insert_decision(
            connection,
            native_id="a" * 32,
            target_id="062A",
            tier="download",
            rule_name="id_segment_exact",
            decided_at="2026-06-22T10:00:01.000000+00:00",
        )

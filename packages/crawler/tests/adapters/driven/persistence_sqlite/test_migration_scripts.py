from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.errors import MigrationError
from p2pwatch.adapters.driven.persistence_sqlite.migration_scripts import Migration, load_scripts

_NO_TRANSACTION = "-- migration: no-transaction\n"
_COPY_BEFORE = "-- migration: copy-before\n"


def test_load_scripts_orders_by_name_and_skips_non_sql(tmp_path: Path) -> None:
    (tmp_path / "0002_second.sql").write_text("B", encoding="utf-8")
    (tmp_path / "0001_premier.sql").write_text("A", encoding="utf-8")
    (tmp_path / "README.md").write_text("ignored", encoding="utf-8")
    assert load_scripts(tmp_path) == (
        Migration(version=1, script="A"),
        Migration(version=2, script="B"),
    )


def test_load_scripts_rejects_a_non_numeric_prefix(tmp_path: Path) -> None:
    (tmp_path / "abcd_mauvais.sql").write_text("X", encoding="utf-8")
    with pytest.raises(MigrationError, match="abcd_mauvais.sql"):
        load_scripts(tmp_path)


# --- Hardening (adversarial review post-6c389b1) ---


def test_load_scripts_rejects_duplicate_version_numbers(tmp_path: Path) -> None:
    (tmp_path / "0001_a.sql").write_text("A", encoding="utf-8")
    (tmp_path / "0001_b.sql").write_text("B", encoding="utf-8")
    with pytest.raises(MigrationError, match="increasing"):
        load_scripts(tmp_path)


def test_load_scripts_rejects_non_padded_prefixes_that_misorder(tmp_path: Path) -> None:
    # Lexicographic sort: "10_b.sql" < "2_a.sql" -> versions (10, 2), not increasing.
    (tmp_path / "2_a.sql").write_text("A", encoding="utf-8")
    (tmp_path / "10_b.sql").write_text("B", encoding="utf-8")
    with pytest.raises(MigrationError, match="increasing"):
        load_scripts(tmp_path)


# --- The directives (stage 1 spec, D8) ---


def test_load_scripts_reads_the_no_transaction_directive(tmp_path: Path) -> None:
    (tmp_path / "0001_plain.sql").write_text("A", encoding="utf-8")
    (tmp_path / "0002_vacuum.sql").write_text(_NO_TRANSACTION + "VACUUM;", encoding="utf-8")
    assert load_scripts(tmp_path) == (
        Migration(version=1, script="A", transactional=True),
        Migration(version=2, script=_NO_TRANSACTION + "VACUUM;", transactional=False),
    )


def test_load_scripts_reads_the_copy_before_directive(tmp_path: Path) -> None:
    (tmp_path / "0001_plain.sql").write_text("A", encoding="utf-8")
    (tmp_path / "0002_drop.sql").write_text(_COPY_BEFORE + "DROP TABLE t;", encoding="utf-8")
    assert load_scripts(tmp_path) == (
        Migration(version=1, script="A", copy_before=False),
        Migration(version=2, script=_COPY_BEFORE + "DROP TABLE t;", copy_before=True),
    )


def test_load_scripts_rejects_a_misspelled_copy_before_directive(tmp_path: Path) -> None:
    (tmp_path / "0001_typo.sql").write_text(
        "-- migration: copy-befor\nDROP TABLE t;", encoding="utf-8"
    )
    with pytest.raises(MigrationError, match="0001_typo.sql.*copy-befor'"):
        load_scripts(tmp_path)


def test_load_scripts_rejects_a_misspelled_directive(tmp_path: Path) -> None:
    (tmp_path / "0001_typo.sql").write_text(
        "-- migration: no-transction\nVACUUM;", encoding="utf-8"
    )
    with pytest.raises(MigrationError, match="0001_typo.sql.*no-transction"):
        load_scripts(tmp_path)

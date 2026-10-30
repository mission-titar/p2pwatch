"""Every shipped migration script carries ``copy-before`` exactly when sqlfluff's parse of it holds
a statement that deletes or rewrites rows."""

from importlib import resources

import pytest
from sqlfluff.core import Linter
from sqlfluff.core.parser import BaseSegment

_MIGRATIONS = resources.files("p2pwatch.adapters.driven.persistence_sqlite") / "migrations"
_COPY_BEFORE = "-- migration: copy-before\n"
_ROW_CHANGING_STATEMENTS = ("delete_statement", "update_statement", "drop_table_statement")
# A trigger's body runs on later writes, not when the script creates the trigger.
_TRIGGER = "create_trigger"


def _has_keyword(segment: BaseSegment, *, keyword: str) -> bool:
    return any(
        child.is_type("keyword") and child.raw.upper() == keyword for child in segment.segments
    )


def _insert_rewrites_rows(insert: BaseSegment) -> bool:
    """``INSERT ... SELECT`` copies rows; ``REPLACE`` and an upsert's ``DO UPDATE`` rewrite them."""
    return (
        next(insert.recursive_crawl("select_statement"), None) is not None
        or _has_keyword(insert, keyword="REPLACE")
        or any(
            _has_keyword(upsert, keyword="UPDATE")
            for upsert in insert.recursive_crawl("upsert_clause")
        )
    )


def _rewrites_rows(script: str) -> bool:
    tree = Linter(dialect="sqlite").parse_string(script).tree
    assert tree is not None
    if any(
        next(tree.recursive_crawl(kind, no_recursive_seg_type=_TRIGGER), None)
        for kind in _ROW_CHANGING_STATEMENTS
    ):
        return True
    if any(
        _insert_rewrites_rows(insert)
        for insert in tree.recursive_crawl("insert_statement", no_recursive_seg_type=_TRIGGER)
    ):
        return True
    # SQLite's one ALTER TABLE that drops anything is DROP COLUMN.
    return any(
        _has_keyword(alter, keyword="DROP")
        for alter in tree.recursive_crawl("alter_table_statement")
    )


def _mismatched_scripts(scripts_by_name: dict[str, str]) -> list[str]:
    return sorted(
        name
        for name, script in scripts_by_name.items()
        if script.startswith(_COPY_BEFORE) != _rewrites_rows(script)
    )


def _shipped_scripts() -> dict[str, str]:
    return {
        f"{database}/{script_file.name}": script_file.read_text(encoding="utf-8")
        for database in ("catalog", "local")
        for script_file in (_MIGRATIONS / database).iterdir()
        if script_file.name.endswith(".sql")
    }


def test_the_shipped_scripts_carry_copy_before_exactly_when_they_rewrite_rows() -> None:
    assert _mismatched_scripts(_shipped_scripts()) == []


def test_a_shipped_script_rewriting_rows_without_the_directive_is_found() -> None:
    scripts_by_name = _shipped_scripts()
    name = "catalog/0006_drop_dead_tables.sql"
    scripts_by_name[name] = scripts_by_name[name].removeprefix(_COPY_BEFORE)
    assert _mismatched_scripts(scripts_by_name) == [name]


def test_a_shipped_script_carrying_the_directive_without_rewriting_rows_is_found() -> None:
    scripts_by_name = _shipped_scripts()
    name = "catalog/0013_raw_metadata.sql"
    scripts_by_name[name] = _COPY_BEFORE + scripts_by_name[name]
    assert _mismatched_scripts(scripts_by_name) == [name]


@pytest.mark.parametrize(
    "script",
    [
        "ALTER TABLE a DROP COLUMN b;\n",
        "DELETE FROM a;\n",
        "UPDATE a SET b = 1;\n",
        "DROP TABLE a;\n",
        "INSERT INTO a SELECT b FROM c;\n",
        "INSERT OR REPLACE INTO a VALUES (1);\n",
        "REPLACE INTO a VALUES (1);\n",
        "INSERT INTO a VALUES (1) ON CONFLICT (b) DO UPDATE SET c = 1;\n",
    ],
)
def test_an_unmarked_script_rewriting_rows_is_found(script: str) -> None:
    assert _mismatched_scripts({"0001_script.sql": script}) == ["0001_script.sql"]


@pytest.mark.parametrize(
    "script",
    [
        "ALTER TABLE a ADD COLUMN b INTEGER;\n",
        "ALTER TABLE a RENAME COLUMN b TO c;\n",
        "INSERT INTO a VALUES (1);\n",
        "INSERT INTO a VALUES (1) ON CONFLICT DO NOTHING;\n",
        "CREATE TRIGGER t AFTER INSERT ON a BEGIN DELETE FROM b; INSERT INTO c SELECT 1; END;\n",
        "SELECT 'DELETE FROM a';\n",
        "-- DELETE FROM a\nCREATE INDEX i ON a (b);\n",
    ],
)
def test_an_unmarked_script_rewriting_no_row_matches(script: str) -> None:
    assert _mismatched_scripts({"0001_script.sql": script}) == []

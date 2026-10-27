"""Every shipped migration script carries ``copy-before`` exactly when sqlfluff's parse of it holds
a statement that deletes or rewrites rows."""

from importlib import resources

import pytest
from sqlfluff.core import Linter

_MIGRATIONS = resources.files("p2pwatch.adapters.driven.persistence_sqlite") / "migrations"
_COPY_BEFORE = "-- migration: copy-before\n"
_ROW_CHANGING_STATEMENTS = ("delete_statement", "update_statement", "drop_table_statement")


def _rewrites_rows(script: str) -> bool:
    tree = Linter(dialect="sqlite").parse_string(script).tree
    assert tree is not None
    if any(next(tree.recursive_crawl(kind), None) for kind in _ROW_CHANGING_STATEMENTS):
        return True
    if any(
        next(insert.recursive_crawl("select_statement"), None)
        for insert in tree.recursive_crawl("insert_statement")
    ):
        return True
    # SQLite's one ALTER TABLE that drops anything is DROP COLUMN.
    return any(
        segment.is_type("keyword") and segment.raw.upper() == "DROP"
        for alter in tree.recursive_crawl("alter_table_statement")
        for segment in alter.segments
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
        "SELECT 'DELETE FROM a';\n",
        "-- DELETE FROM a\nCREATE INDEX i ON a (b);\n",
    ],
)
def test_an_unmarked_script_rewriting_no_row_matches(script: str) -> None:
    assert _mismatched_scripts({"0001_script.sql": script}) == []

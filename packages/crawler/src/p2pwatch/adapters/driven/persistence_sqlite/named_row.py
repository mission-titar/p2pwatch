"""A row read by column name only: a read by index or by unpacking fails at once."""

import sqlite3
from typing import Any, NoReturn


class NamedRow(dict[str, Any]):
    """A row's values by column name; ``row[0]`` raises ``KeyError``, unpacking ``TypeError``."""

    def __iter__(self) -> NoReturn:
        raise TypeError("a row is read by column name")


def named_row(cursor: sqlite3.Cursor, values: tuple[Any, ...]) -> NamedRow:
    """The row factory: refuses a column name that appears twice, which a dict would keep once."""
    names = [column[0] for column in cursor.description]
    for name in names:
        if names.count(name) > 1:
            raise ValueError(f"the column {name!r} appears twice")
    return NamedRow(zip(names, values, strict=True))

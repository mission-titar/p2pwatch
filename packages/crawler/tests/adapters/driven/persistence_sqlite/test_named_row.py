from typing import Any

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.named_row import NamedRow


def _row() -> Any:
    """``Any``, as a cursor's ``fetchone`` types it."""
    return NamedRow({"a": 1, "b": "x"})


def test_a_row_is_read_by_column_name() -> None:
    row = _row()
    assert row["a"] == 1
    assert row["b"] == "x"
    assert row == {"a": 1, "b": "x"}
    assert dict(row) == {"a": 1, "b": "x"}
    assert list(row.items()) == [("a", 1), ("b", "x")]


def test_a_read_by_index_raises() -> None:
    with pytest.raises(KeyError):
        _row()[0]


def test_unpacking_a_row_raises() -> None:
    row = _row()
    with pytest.raises(TypeError, match="by column name"):
        a, b = row
    with pytest.raises(TypeError, match="by column name"):
        print(*row)

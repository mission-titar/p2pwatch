"""A row read by column name only: a read by index or by unpacking fails at once."""

from typing import Any, NoReturn


class NamedRow(dict[str, Any]):
    """A row's values by column name; ``row[0]`` raises ``KeyError``, unpacking ``TypeError``."""

    def __iter__(self) -> NoReturn:
        raise TypeError("a row is read by column name")

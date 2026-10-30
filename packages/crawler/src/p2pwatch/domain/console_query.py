"""A query the console runs on one of the node's databases, and its answer."""

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum


class ConsoleDatabase(StrEnum):
    CATALOG = "catalog"
    LOCAL = "local"


@dataclass(kw_only=True, frozen=True)
class QueryAnswer:
    """A query's columns and first rows, each cell as text: ``NULL``, a blob in lowercase hex."""

    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    elapsed: timedelta
    truncated: bool  # more rows than the cap, which were dropped


@dataclass(kw_only=True, frozen=True)
class QueryFailure:
    """Why a query gave no answer, as the operator reads it."""

    message: str

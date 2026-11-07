"""``ConfigProblem``: one problem of a config file."""

from dataclasses import dataclass
from pathlib import PurePath


@dataclass(kw_only=True, frozen=True)
class ConfigProblem:
    """What a config file holds wrong: ``key`` is the key path it names, ``None`` for none."""

    file_path: PurePath
    key: str | None
    message: str

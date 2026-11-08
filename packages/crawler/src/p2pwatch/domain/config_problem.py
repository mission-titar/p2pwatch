"""``ConfigProblem``: one problem of a config file, and the key path it names."""

from dataclasses import dataclass
from pathlib import PurePath


@dataclass(kw_only=True, frozen=True)
class ConfigProblem:
    """What a config file holds wrong: ``key`` is the key path it names, ``None`` for none."""

    file_path: PurePath
    key: str | None
    message: str


def key_path(*parts: str | int) -> str:
    """The path of ``parts`` as a problem names it, ``search.keywords[0]``: a string a key, its
    characters a terminal would not print escaped, an integer an index."""
    segments = (f"[{part}]" if isinstance(part, int) else f".{_printable(part)}" for part in parts)
    return "".join(segments).removeprefix(".")


def _printable(key: str) -> str:
    return "".join(
        character if character.isprintable() else character.encode("unicode_escape").decode()
        for character in key
    )

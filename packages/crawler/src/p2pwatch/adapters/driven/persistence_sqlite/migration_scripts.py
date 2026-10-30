"""The ``NNNN_*.sql`` migration scripts, read from a directory, and those a database has pending."""

from dataclasses import dataclass
from importlib.resources.abc import Traversable
from itertools import pairwise

from p2pwatch.adapters.driven.persistence_sqlite.errors import MigrationError

_DIRECTIVE = "-- migration:"
_NO_TRANSACTION = "-- migration: no-transaction"
_COPY_BEFORE = "-- migration: copy-before"


@dataclass(kw_only=True, frozen=True)
class Migration:
    version: int
    script: str
    transactional: bool = True
    copy_before: bool = False


@dataclass(kw_only=True, frozen=True)
class PendingMigrations:
    """The migrations above a database's version. By a convention the type makes visible, only
    ``SqliteDatabaseOpener`` builds one, once it has read that version."""

    current_version: int
    migrations: tuple[Migration, ...]


def load_scripts(directory: Traversable) -> tuple[Migration, ...]:
    """The ``NNNN_*.sql`` scripts by name; a bad name, a misordered version or an unknown
    directive raises ``MigrationError`` (non-``.sql`` files are ignored, gaps allowed)."""
    scripts: list[Migration] = []
    for script_file in sorted(directory.iterdir(), key=lambda script_file: script_file.name):
        if not script_file.name.endswith(".sql"):
            continue
        prefix = script_file.name.partition("_")[0]
        if not prefix.isdigit():
            raise MigrationError(f"invalid script name (NNNN_*.sql expected): {script_file.name}")
        script = script_file.read_text(encoding="utf-8")
        scripts.append(_read_directive(int(prefix), name=script_file.name, script=script))
    for left, right in pairwise(script.version for script in scripts):
        if right <= left:
            raise MigrationError(
                f"migration versions not strictly increasing: {left} then {right} "
                "(unique zero-padded NNNN prefixes required)"
            )
    return tuple(scripts)


def _read_directive(version: int, *, name: str, script: str) -> Migration:
    first_line = script.partition("\n")[0]
    if first_line == _NO_TRANSACTION:
        return Migration(version=version, script=script, transactional=False)
    if first_line == _COPY_BEFORE:
        return Migration(version=version, script=script, copy_before=True)
    if first_line.startswith(_DIRECTIVE):
        raise MigrationError(
            f"{name}: unknown directive {first_line!r}, "
            f"only {_NO_TRANSACTION!r} or {_COPY_BEFORE!r}"
        )
    return Migration(version=version, script=script)

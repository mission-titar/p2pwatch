"""The pre-migration copies a test finds beside a database."""

from datetime import UTC, datetime
from pathlib import Path


def pre_migration_copies(directory: Path) -> list[tuple[str, datetime]]:
    """Each pre-migration copy in ``directory``, by name: its name before the instant, and the
    instant."""
    copies = []
    for name in sorted(file.name for file in directory.iterdir() if ".pre-" in file.name):
        prefix, _, stamp = name.rpartition(".")
        instant = datetime.strptime(stamp, "%Y-%m-%d_%H-%M-%S_UTC").replace(tzinfo=UTC)
        copies.append((prefix, instant))
    return copies

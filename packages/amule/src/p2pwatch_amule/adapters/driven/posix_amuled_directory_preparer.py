from collections.abc import Callable, Sequence
from pathlib import Path

from p2pwatch_amule.application.ports.driven.amuled_directory_preparer import (
    AmuledDirectoryPreparer,
)


class PosixAmuledDirectoryPreparer(AmuledDirectoryPreparer):
    """Creates every owned directory, then chowns each through ``change_owner``."""

    def __init__(
        self,
        *,
        owned_directories: Sequence[Path],
        change_owner: Callable[[Path, int, int], None],
    ) -> None:
        self._owned_directories = owned_directories
        self._change_owner = change_owner

    def prepare_amuled_directories(self, uid: int, gid: int) -> None:
        for directory in self._owned_directories:
            directory.mkdir(parents=True, exist_ok=True)
        # Not recursive: the mounts can hold hundreds of gigabytes of part files the operator owns.
        for directory in self._owned_directories:
            self._change_owner(directory, uid, gid)

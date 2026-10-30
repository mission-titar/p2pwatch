from p2pwatch_amule.application.ports.driven.amuled_directory_preparer import (
    AmuledDirectoryPreparer,
)
from p2pwatch_amule.domain.identifiers import Gid, Uid


class FakeAmuledDirectoryPreparer(AmuledDirectoryPreparer):
    """Records each preparation it is asked for in ``actions``."""

    def __init__(self, actions: list[str]) -> None:
        self.actions = actions

    def prepare_amuled_directories(self, uid: Uid, *, gid: Gid) -> None:
        self.actions.append(f"directories {uid}:{gid}")

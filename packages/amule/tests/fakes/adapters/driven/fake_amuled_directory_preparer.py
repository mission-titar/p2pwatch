from p2pwatch_amule.application.ports.driven.amuled_directory_preparer import (
    AmuledDirectoryPreparer,
)


class FakeAmuledDirectoryPreparer(AmuledDirectoryPreparer):
    """Records each preparation it is asked for in ``actions``."""

    def __init__(self, actions: list[str]) -> None:
        self.actions = actions

    def prepare_amuled_directories(self, uid: int, gid: int) -> None:
        self.actions.append(f"directories {uid}:{gid}")

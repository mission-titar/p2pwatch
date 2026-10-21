"""PosixAccountManager: groupadd then useradd, each only when its lookup misses."""

import subprocess
from pathlib import Path
from typing import Any

from p2pwatch_amule.adapters.driven.posix_account_manager import PosixAccountManager

HOME_DIRECTORY = Path("/home/amule")


class FakeSystem:
    """The account lookups, ``amule`` present or not, and the commands run, recorded."""

    def __init__(self, *, has_amule_account: bool) -> None:
        self.has_amule_account = has_amule_account
        self.commands: list[tuple[list[str], dict[str, Any]]] = []

    def find(self, name: str) -> object:
        assert name == "amule"
        if not self.has_amule_account:
            raise KeyError(name)
        return object()

    def run_command(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.commands.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0)

    def account_manager(self) -> PosixAccountManager:
        return PosixAccountManager(
            home_directory=HOME_DIRECTORY,
            run_command=self.run_command,
            find_group=self.find,
            find_user=self.find,
        )


def test_a_missing_account_is_created_group_first() -> None:
    system = FakeSystem(has_amule_account=False)

    system.account_manager().find_or_create_amule_account(1000, 1001)

    useradd = ["useradd", "-o", "-u", "1000", "-g", "1001", "-M", "-d", "/home/amule"]
    assert system.commands == [
        (["groupadd", "-o", "-g", "1001", "amule"], {"check": True}),
        ([*useradd, "-s", "/usr/sbin/nologin", "amule"], {"check": True}),
    ]


def test_an_existing_account_is_not_recreated() -> None:
    system = FakeSystem(has_amule_account=True)

    system.account_manager().find_or_create_amule_account(1000, 1001)

    assert system.commands == []

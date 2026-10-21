"""PosixAccountManager: groupadd then useradd, each only when its own lookup misses."""

from collections.abc import Callable
from pathlib import Path

from p2pwatch_amule.adapters.driven.posix_account_manager import PosixAccountManager
from tests.fakes import FakeCommandRunner

HOME_DIRECTORY = Path("/home/amule")
GROUPADD = ["groupadd", "-o", "-g", "1001", "amule"]
USERADD = ["useradd", "-o", "-u", "1000", "-g", "1001", "-M", "-d", "/home/amule"]
USERADD_NOLOGIN = [*USERADD, "-s", "/usr/sbin/nologin", "amule"]


def _lookup(*, is_present: bool) -> Callable[[str], object]:
    """A ``getgrnam`` or ``getpwnam`` that finds ``amule`` or raises ``KeyError``."""

    def find(name: str) -> object:
        assert name == "amule"
        if not is_present:
            raise KeyError(name)
        return object()

    return find


def _account_manager(
    command_runner: FakeCommandRunner, *, has_group: bool, has_user: bool
) -> PosixAccountManager:
    return PosixAccountManager(
        home_directory=HOME_DIRECTORY,
        run_command=command_runner.run_command,
        find_group=_lookup(is_present=has_group),
        find_user=_lookup(is_present=has_user),
    )


def test_a_missing_account_is_created_group_first() -> None:
    command_runner = FakeCommandRunner()

    _account_manager(command_runner, has_group=False, has_user=False).find_or_create_amule_account(
        1000, 1001
    )

    assert command_runner.commands == [
        (GROUPADD, {"check": True}),
        (USERADD_NOLOGIN, {"check": True}),
    ]


def test_an_existing_group_is_kept_and_the_missing_user_created() -> None:
    command_runner = FakeCommandRunner()

    _account_manager(command_runner, has_group=True, has_user=False).find_or_create_amule_account(
        1000, 1001
    )

    assert command_runner.commands == [(USERADD_NOLOGIN, {"check": True})]


def test_an_existing_account_is_not_recreated() -> None:
    command_runner = FakeCommandRunner()

    _account_manager(command_runner, has_group=True, has_user=True).find_or_create_amule_account(
        1000, 1001
    )

    assert command_runner.commands == []

"""PosixAccountProvisioner: groupadd then useradd, each only when its own lookup misses."""

from pathlib import Path

from p2pwatch_amule.adapters.driven.posix_account_provisioner import (
    AccountFinder,
    CommandRunner,
    PosixAccountProvisioner,
)
from p2pwatch_amule.domain.identifiers import Gid, Uid
from tests.fakes.adapters.driven.fake_command_runner import FakeCommandRunner

HOME_DIRECTORY = Path("/home/amule")
GROUPADD = ["groupadd", "-o", "-g", "1001", "amule"]
USERADD = ["useradd", "-o", "-u", "1000", "-g", "1001", "-M", "-d", "/home/amule"]
USERADD_NOLOGIN = [*USERADD, "-s", "/usr/sbin/nologin", "amule"]
CHECKED = {"check": True, "text": True}


def _lookup(*, is_present: bool) -> AccountFinder:
    """A ``getgrnam`` or ``getpwnam`` that finds ``amule`` or raises ``KeyError``."""

    def find(name: str) -> object:
        assert name == "amule"
        if not is_present:
            raise KeyError(name)
        return object()

    return find


def _account_provisioner(
    command_runner: FakeCommandRunner, *, has_group: bool, has_user: bool
) -> PosixAccountProvisioner:
    return PosixAccountProvisioner(
        home_directory=HOME_DIRECTORY,
        run_command=command_runner.run_command,
        find_group=_lookup(is_present=has_group),
        find_user=_lookup(is_present=has_user),
    )


def test_a_missing_account_is_created_group_first() -> None:
    command_runner = FakeCommandRunner()

    _account_provisioner(
        command_runner, has_group=False, has_user=False
    ).find_or_create_amule_account(Uid(1000), gid=Gid(1001))

    assert command_runner.commands == [
        (GROUPADD, CHECKED),
        (USERADD_NOLOGIN, CHECKED),
    ]


def test_an_existing_group_is_kept_and_the_missing_user_created() -> None:
    command_runner = FakeCommandRunner()

    _account_provisioner(
        command_runner, has_group=True, has_user=False
    ).find_or_create_amule_account(Uid(1000), gid=Gid(1001))

    assert command_runner.commands == [(USERADD_NOLOGIN, CHECKED)]


def test_an_existing_account_is_not_recreated() -> None:
    command_runner = FakeCommandRunner()

    _account_provisioner(
        command_runner, has_group=True, has_user=True
    ).find_or_create_amule_account(Uid(1000), gid=Gid(1001))

    assert command_runner.commands == []


def test_mypy_refuses_a_command_runner_text_false() -> None:
    run_command: CommandRunner = FakeCommandRunner().run_command
    # The ignore is the test: strict mypy reports it unused if CommandRunner admits text=False.
    run_command(GROUPADD, check=True, text=False)  # type: ignore[arg-type]

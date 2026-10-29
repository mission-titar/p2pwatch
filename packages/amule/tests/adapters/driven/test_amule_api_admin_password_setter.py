"""AmuleApiAdminPasswordSetter: ``amuleapi --set-admin-pass`` run as the uid and gid given."""

from pathlib import Path

from p2pwatch_amule.adapters.driven.amule_api_admin_password_setter import (
    AmuleApiAdminPasswordSetter,
    CommandRunner,
)
from p2pwatch_amule.domain.identifiers import Gid, Uid
from tests.fakes.adapters.driven.fake_command_runner import FakeCommandRunner

HOME_DIRECTORY = Path("/home/amule")
CONFIG_DIRECTORY = HOME_DIRECTORY / ".aMule"
ENV = {"PATH": "/usr/local/bin:/usr/bin", "HOME": "/root", "PUID": "1000"}


def _admin_password_setter(command_runner: FakeCommandRunner) -> AmuleApiAdminPasswordSetter:
    return AmuleApiAdminPasswordSetter(
        config_directory=CONFIG_DIRECTORY,
        home_directory=HOME_DIRECTORY,
        env=ENV,
        run_command=command_runner.run_command,
    )


def test_amuleapi_sets_the_password_as_the_uid_and_gid_alone() -> None:
    command_runner = FakeCommandRunner()

    _admin_password_setter(command_runner).set_admin_password("mot de passé", Uid(1000), Gid(1001))

    argv = ["amuleapi", "--config-dir=/home/amule/.aMule", "--set-admin-pass=mot de passé"]
    assert command_runner.commands == [
        (
            argv,
            {
                "user": 1000,
                "group": 1001,
                "extra_groups": [],
                "env": {**ENV, "HOME": "/home/amule"},
                "check": True,
                "text": True,
            },
        )
    ]


def test_mypy_refuses_a_command_runner_text_false() -> None:
    run_command: CommandRunner = FakeCommandRunner().run_command
    # The ignore is the test: strict mypy reports it unused if CommandRunner admits text=False.
    run_command(
        ["amuleapi"],
        user=Uid(1000),
        group=Gid(1001),
        extra_groups=[],
        env=ENV,
        check=True,
        text=False,  # type: ignore[arg-type]
    )

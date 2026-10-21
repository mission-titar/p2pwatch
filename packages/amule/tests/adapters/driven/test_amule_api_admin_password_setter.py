"""AmuleApiAdminPasswordSetter: ``amuleapi --set-admin-pass`` run as the uid and gid given."""

import subprocess
from pathlib import Path
from typing import Any

from p2pwatch_amule.adapters.driven.amule_api_admin_password_setter import (
    AmuleApiAdminPasswordSetter,
)

HOME_DIRECTORY = Path("/home/amule")
CONFIG_DIRECTORY = HOME_DIRECTORY / ".aMule"
ENV = {"PATH": "/usr/local/bin:/usr/bin", "HOME": "/root", "PUID": "1000"}


class FakeSystem:
    """Records the commands run: the gate cannot run a command as another uid."""

    def __init__(self) -> None:
        self.commands: list[tuple[list[str], dict[str, Any]]] = []

    def run_command(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.commands.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0)

    def admin_password_setter(self) -> AmuleApiAdminPasswordSetter:
        return AmuleApiAdminPasswordSetter(
            config_directory=CONFIG_DIRECTORY,
            home_directory=HOME_DIRECTORY,
            env=ENV,
            run_command=self.run_command,
        )


def test_amuleapi_sets_the_password_as_the_uid_and_gid_alone() -> None:
    system = FakeSystem()

    system.admin_password_setter().set_admin_password("mot de passé", 1000, 1001)

    argv = ["amuleapi", "--config-dir=/home/amule/.aMule", "--set-admin-pass=mot de passé"]
    assert system.commands == [
        (
            argv,
            {
                "user": 1000,
                "group": 1001,
                "extra_groups": [],
                "env": {**ENV, "HOME": "/home/amule"},
                "check": True,
            },
        )
    ]

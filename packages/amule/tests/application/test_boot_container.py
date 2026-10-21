"""BootContainer: every variable refused first, then the account, then the mount points."""

import re

import pytest

from p2pwatch_amule.application.boot_container import BootContainer
from p2pwatch_amule.domain.settings_error import SettingsError
from tests.fakes import FakeAccountManager, FakeMountPointPreparer

ENV = {
    "PUID": "1000",
    "PGID": "1001",
    "AMULE_EC_PASSWORD": "hunter2",
    "AMULE_API_PASSWORD": "s3cret",
}


class Booter:
    """A BootContainer over the package's fakes."""

    def __init__(self) -> None:
        self.account_manager = FakeAccountManager()
        self.mount_point_preparer = FakeMountPointPreparer()
        self.container_booter = BootContainer(
            account_manager=self.account_manager,
            mount_point_preparer=self.mount_point_preparer,
        )


def test_the_account_takes_puid_and_pgid() -> None:
    booter = Booter()

    booter.container_booter.boot_container(ENV)

    assert booter.account_manager.accounts == [(1000, 1001)]


def test_the_mount_points_are_owned_by_puid_and_pgid() -> None:
    booter = Booter()

    booter.container_booter.boot_container(ENV)

    assert booter.mount_point_preparer.owners == [(1000, 1001)]


@pytest.mark.parametrize(
    ("variables", "message"),
    [
        ({"PUID": ""}, "PUID is required"),
        ({"PGID": "amule"}, "PGID must be a numeric id, got 'amule'"),
        ({"AMULE_API_PASSWORD": "s3cret\n"}, "AMULE_API_PASSWORD must not contain a control"),
        ({"PORT_SYNC": "maybe"}, "PORT_SYNC must be one of "),
        ({"PORT_SYNC": "on", "PORT_SYNC_POLL_SECONDS": "0"}, "PORT_SYNC_POLL_SECONDS must be "),
        ({"PORT_SYNC": "yes", "GLUETUN_CONTROL_URL": "gluetun"}, "GLUETUN_CONTROL_URL must be "),
    ],
)
def test_a_refused_variable_aborts_the_boot_before_any_change(
    variables: dict[str, str], message: str
) -> None:
    booter = Booter()

    with pytest.raises(SettingsError, match=f"^{re.escape(message)}"):
        booter.container_booter.boot_container({**ENV, **variables})

    assert booter.account_manager.accounts == []
    assert booter.mount_point_preparer.owners == []


def test_port_sync_off_leaves_its_other_variables_unread() -> None:
    booter = Booter()
    env = {**ENV, "PORT_SYNC": "off", "PORT_SYNC_POLL_SECONDS": "0"}

    booter.container_booter.boot_container(env)

    assert booter.account_manager.accounts == [(1000, 1001)]

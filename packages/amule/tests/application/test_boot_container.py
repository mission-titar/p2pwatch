"""BootContainer: every variable refused first, then the account."""

import re

import pytest

from p2pwatch_amule.application.boot_container import BootContainer
from p2pwatch_amule.domain.settings_error import SettingsError
from tests.fakes import FakeAccountManager

ENV = {
    "PUID": "1000",
    "PGID": "1001",
    "AMULE_EC_PASSWORD": "hunter2",
    "AMULE_API_PASSWORD": "s3cret",
}


def test_the_account_takes_puid_and_pgid() -> None:
    account_manager = FakeAccountManager()

    BootContainer(account_manager=account_manager).boot_container(ENV)

    assert account_manager.accounts == [(1000, 1001)]


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
def test_a_refused_variable_aborts_the_boot_before_the_account(
    variables: dict[str, str], message: str
) -> None:
    account_manager = FakeAccountManager()

    with pytest.raises(SettingsError, match=f"^{re.escape(message)}"):
        BootContainer(account_manager=account_manager).boot_container({**ENV, **variables})

    assert account_manager.accounts == []


def test_port_sync_off_leaves_its_other_variables_unread() -> None:
    account_manager = FakeAccountManager()
    env = {**ENV, "PORT_SYNC": "off", "PORT_SYNC_POLL_SECONDS": "0"}

    BootContainer(account_manager=account_manager).boot_container(env)

    assert account_manager.accounts == [(1000, 1001)]

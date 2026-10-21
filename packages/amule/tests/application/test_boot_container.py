"""BootContainer: every variable refused first, then the account, directories, conf, password."""

import hashlib
import re

import pytest

from p2pwatch_amule.application.boot_container import BootContainer
from p2pwatch_amule.domain.conf import reconcile_conf
from p2pwatch_amule.domain.settings_error import SettingsError
from tests.fakes import (
    FakeAccountManager,
    FakeAdminPasswordSetter,
    FakeAmuleConf,
    FakeAmuledDirectoryPreparer,
)

DIGEST = hashlib.md5(b"hunter2").hexdigest()

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
        self.amuled_directory_preparer = FakeAmuledDirectoryPreparer()
        self.amule_conf = FakeAmuleConf()
        self.admin_password_setter = FakeAdminPasswordSetter()
        self.container_booter = BootContainer(
            account_manager=self.account_manager,
            amuled_directory_preparer=self.amuled_directory_preparer,
            amule_conf_reader=self.amule_conf,
            amule_conf_writer=self.amule_conf,
            admin_password_setter=self.admin_password_setter,
        )


def test_the_account_takes_puid_and_pgid() -> None:
    booter = Booter()

    booter.container_booter.boot_container(ENV)

    assert booter.account_manager.accounts == [(1000, 1001)]


def test_the_amuled_directories_are_owned_by_puid_and_pgid() -> None:
    booter = Booter()

    booter.container_booter.boot_container(ENV)

    assert booter.amuled_directory_preparer.owners == [(1000, 1001)]


def test_first_boot_writes_the_minimal_conf_owned_by_puid_and_pgid() -> None:
    booter = Booter()

    booter.container_booter.boot_container(ENV)

    assert booter.amule_conf.conf == reconcile_conf(None, DIGEST)
    assert booter.amule_conf.owners == [(1000, 1001)]


def test_an_existing_conf_is_reconciled_not_replaced() -> None:
    booter = Booter()
    existing_conf = "[eMule]\nMaxUpload=42\n\n[ExternalConnect]\nECPassword=dead\n"
    booter.amule_conf.conf = existing_conf

    booter.container_booter.boot_container(ENV)

    assert booter.amule_conf.conf == reconcile_conf(existing_conf, DIGEST)


@pytest.mark.parametrize("api_password", ["s3cret", "mot de passé"])
def test_the_admin_password_is_the_one_given_set_as_puid_and_pgid(api_password: str) -> None:
    booter = Booter()

    booter.container_booter.boot_container({**ENV, "AMULE_API_PASSWORD": api_password})

    assert booter.admin_password_setter.passwords == [(api_password, 1000, 1001)]


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
    assert booter.amuled_directory_preparer.owners == []
    assert booter.amule_conf.owners == []
    assert booter.admin_password_setter.passwords == []


def test_port_sync_off_leaves_its_other_variables_unread() -> None:
    booter = Booter()
    env = {**ENV, "PORT_SYNC": "off", "PORT_SYNC_POLL_SECONDS": "0"}

    booter.container_booter.boot_container(env)

    assert booter.account_manager.accounts == [(1000, 1001)]

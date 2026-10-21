"""BootContainer: every variable refused first, then each step, port-sync's state last."""

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
    FakeServiceSupervisor,
)

DIGEST = hashlib.md5(b"hunter2").hexdigest()

ENV = {
    "PUID": "1000",
    "PGID": "1001",
    "AMULE_EC_PASSWORD": "hunter2",
    "AMULE_API_PASSWORD": "s3cret",
}


class Booter:
    """A BootContainer over the package's fakes, each recording into one action list."""

    def __init__(self) -> None:
        self.actions: list[str] = []
        self.amule_conf = FakeAmuleConf(self.actions)
        self.container_booter = BootContainer(
            account_manager=FakeAccountManager(self.actions),
            amuled_directory_preparer=FakeAmuledDirectoryPreparer(self.actions),
            amule_conf_reader=self.amule_conf,
            amule_conf_writer=self.amule_conf,
            admin_password_setter=FakeAdminPasswordSetter(self.actions),
            service_supervisor=FakeServiceSupervisor(self.actions),
        )


def test_each_step_runs_as_puid_and_pgid_in_order_port_sync_last() -> None:
    booter = Booter()

    booter.container_booter.boot_container(ENV)

    # The password follows the directories: amuleapi writes under .aMule as PUID:PGID.
    assert booter.actions == [
        "account 1000:1001",
        "directories 1000:1001",
        "read amule.conf",
        "write amule.conf as 1000:1001",
        "admin password s3cret as 1000:1001",
        "disable port-sync",
    ]


def test_first_boot_writes_the_minimal_conf() -> None:
    booter = Booter()

    booter.container_booter.boot_container(ENV)

    assert booter.amule_conf.conf == reconcile_conf(None, DIGEST)


def test_an_existing_conf_is_reconciled_not_replaced() -> None:
    booter = Booter()
    existing_conf = "[eMule]\nMaxUpload=42\n\n[ExternalConnect]\nECPassword=dead\n"
    booter.amule_conf.conf = existing_conf

    booter.container_booter.boot_container(ENV)

    assert booter.amule_conf.conf == reconcile_conf(existing_conf, DIGEST)


@pytest.mark.parametrize("api_password", ["s3cret", "mot de passé"])
def test_the_admin_password_is_the_one_given(api_password: str) -> None:
    booter = Booter()

    booter.container_booter.boot_container({**ENV, "AMULE_API_PASSWORD": api_password})

    assert f"admin password {api_password} as 1000:1001" in booter.actions


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

    assert booter.actions == []


def test_port_sync_off_leaves_its_other_variables_unread() -> None:
    booter = Booter()
    env = {**ENV, "PORT_SYNC": "off", "PORT_SYNC_POLL_SECONDS": "0"}

    booter.container_booter.boot_container(env)

    assert booter.actions[-1] == "disable port-sync"


@pytest.mark.parametrize("port_sync", ["off", "", None])
def test_port_sync_off_or_unset_is_disabled(port_sync: str | None) -> None:
    booter = Booter()
    env = ENV if port_sync is None else {**ENV, "PORT_SYNC": port_sync}

    booter.container_booter.boot_container(env)

    assert booter.actions[-1] == "disable port-sync"


@pytest.mark.parametrize("port_sync", ["yes", "On"])
def test_port_sync_on_is_enabled(port_sync: str) -> None:
    booter = Booter()

    booter.container_booter.boot_container({**ENV, "PORT_SYNC": port_sync})

    assert booter.actions[-1] == "enable port-sync"

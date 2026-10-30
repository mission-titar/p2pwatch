"""The boot's composition: the variables parsed at each boot, every one refused before a change."""

import re
from collections.abc import Mapping

import pytest

from p2pwatch_amule.composition.boot_composition import BootComposition
from p2pwatch_amule.domain.settings_error import SettingsError
from tests.fakes.adapters.driven.fake_account_provisioner import FakeAccountProvisioner
from tests.fakes.adapters.driven.fake_admin_password_setter import FakeAdminPasswordSetter
from tests.fakes.adapters.driven.fake_amule_conf_store import FakeAmuleConfStore
from tests.fakes.adapters.driven.fake_amuled_directory_preparer import FakeAmuledDirectoryPreparer
from tests.fakes.adapters.driven.fake_service_supervisor import FakeServiceSupervisor

ENV = {
    "PUID": "1000",
    "PGID": "1001",
    "AMULE_EC_PASSWORD": "hunter2",
    "AMULE_API_PASSWORD": "s3cret",
}


def _boot_composition(env: Mapping[str, str], *, actions: list[str]) -> BootComposition:
    amule_conf = FakeAmuleConfStore(actions)
    return BootComposition(
        env=env,
        account_provisioner=FakeAccountProvisioner(actions),
        amuled_directory_preparer=FakeAmuledDirectoryPreparer(actions),
        amule_conf_reader=amule_conf,
        amule_conf_writer=amule_conf,
        admin_password_setter=FakeAdminPasswordSetter(actions),
        service_supervisor=FakeServiceSupervisor(actions),
    )


def test_the_boot_runs_on_the_settings_its_variables_give() -> None:
    actions: list[str] = []

    _boot_composition({**ENV, "PORT_SYNC": "on"}, actions=actions).boot_container()

    assert actions == [
        "account 1000:1001",
        "directories 1000:1001",
        "read amule.conf",
        "write amule.conf as 1000:1001",
        "admin password s3cret as 1000:1001",
        "enable port-sync",
    ]


@pytest.mark.parametrize(
    ("variables", "message"),
    [
        ({"PUID": ""}, "PUID is required"),
        ({"AMULE_API_PASSWORD": "s3cret\n"}, "AMULE_API_PASSWORD must not contain a control"),
        ({"PORT_SYNC": "on", "GLUETUN_CONTROL_URL": "gluetun"}, "GLUETUN_CONTROL_URL must be "),
    ],
)
def test_a_refused_variable_aborts_the_boot_before_any_change(
    *, variables: dict[str, str], message: str
) -> None:
    actions: list[str] = []
    boot_composition = _boot_composition({**ENV, **variables}, actions=actions)

    with pytest.raises(SettingsError, match=f"^{re.escape(message)}"):
        boot_composition.boot_container()

    assert actions == []

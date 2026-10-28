"""The container's variables: the boot step's, required; port-sync's, with the domain's values."""

import re
from datetime import timedelta

import pytest

from p2pwatch_amule.domain.identifiers import Gid, Uid
from p2pwatch_amule.domain.settings import (
    BootSettings,
    PortSyncSettings,
    is_port_sync_enabled,
    parse_boot_settings,
    parse_port_sync_settings,
)
from p2pwatch_amule.domain.settings_error import SettingsError

BOOT_ENV = {
    "PUID": "1000",
    "PGID": "1001",
    "AMULE_EC_PASSWORD": "hunter2",
    "AMULE_API_PASSWORD": "s3cret",
}
# amule.conf's owner, which port-sync's writes keep as the boot step's do.
IDS = {"PUID": "1000", "PGID": "1001"}


def test_the_boot_variables_give_the_boot_settings() -> None:
    assert parse_boot_settings(BOOT_ENV) == BootSettings(
        uid=Uid(1000),
        gid=Gid(1001),
        ec_password="hunter2",
        api_password="s3cret",
        port_sync_enabled=False,
    )


def test_port_sync_on_is_carried_by_the_boot_settings() -> None:
    assert parse_boot_settings({**BOOT_ENV, "PORT_SYNC": "on"}).port_sync_enabled is True


@pytest.mark.parametrize(
    ("variables", "message"),
    [
        ({"PORT_SYNC": "maybe"}, "PORT_SYNC must be one of "),
        ({"PORT_SYNC": "on", "PORT_SYNC_POLL_SECONDS": "0"}, "PORT_SYNC_POLL_SECONDS must be "),
        ({"PORT_SYNC": "yes", "GLUETUN_CONTROL_URL": "gluetun"}, "GLUETUN_CONTROL_URL must be "),
    ],
)
def test_the_boot_refuses_port_syncs_variables_when_it_is_on(
    variables: dict[str, str], message: str
) -> None:
    with pytest.raises(SettingsError, match=f"^{re.escape(message)}"):
        parse_boot_settings({**BOOT_ENV, **variables})


def test_port_sync_off_leaves_its_other_variables_unread() -> None:
    env = {**BOOT_ENV, "PORT_SYNC": "off", "PORT_SYNC_POLL_SECONDS": "0"}

    assert parse_boot_settings(env).port_sync_enabled is False


@pytest.mark.parametrize("name", list(BOOT_ENV))
@pytest.mark.parametrize("setting", [None, ""])
def test_a_missing_or_empty_boot_variable_is_refused_naming_it(
    name: str, setting: str | None
) -> None:
    env = {key: setting for key, setting in BOOT_ENV.items() if key != name}
    if setting is not None:
        env[name] = setting
    with pytest.raises(SettingsError, match=f"^{name} is required$"):
        parse_boot_settings(env)


def test_the_first_missing_boot_variable_is_the_one_named() -> None:
    with pytest.raises(SettingsError, match="^PUID is required$"):
        parse_boot_settings({})


@pytest.mark.parametrize("name", ["PUID", "PGID"])
@pytest.mark.parametrize("setting", ["amule", "-1", "1 000", "1_000", "+1000", "١٠٠٠"])
def test_a_non_numeric_id_is_refused_naming_it(name: str, setting: str) -> None:
    message = f"{name} must be a numeric id, got {setting!r}"
    with pytest.raises(SettingsError, match=f"^{re.escape(message)}$"):
        parse_boot_settings({**BOOT_ENV, name: setting})


@pytest.mark.parametrize("name", ["AMULE_EC_PASSWORD", "AMULE_API_PASSWORD"])
@pytest.mark.parametrize(
    "password", ["hunter2\n", "hun\tter2", "\rhunter2", "hunter2\x7f", "hunter2\x85"]
)
def test_a_password_with_a_control_character_is_refused_naming_it(name: str, password: str) -> None:
    with pytest.raises(SettingsError, match=f"^{name} must not contain a control character$"):
        parse_boot_settings({**BOOT_ENV, name: password})


def test_a_password_may_hold_spaces_and_non_ascii_letters() -> None:
    env = {**BOOT_ENV, "AMULE_API_PASSWORD": "mot de passé"}
    assert parse_boot_settings(env).api_password == "mot de passé"


@pytest.mark.parametrize("port_sync", ["enabled", "yes", "on", "true", "On", "YES", "True"])
def test_gluetuns_true_values_turn_port_sync_on(port_sync: str) -> None:
    assert is_port_sync_enabled({"PORT_SYNC": port_sync}) is True


@pytest.mark.parametrize("port_sync", ["disabled", "no", "off", "false", "Off", "FALSE", ""])
def test_gluetuns_false_values_and_an_empty_one_turn_it_off(port_sync: str) -> None:
    assert is_port_sync_enabled({"PORT_SYNC": port_sync}) is False


def test_an_unset_port_sync_is_off() -> None:
    assert is_port_sync_enabled({}) is False


@pytest.mark.parametrize("port_sync", ["maybe", "1", "0", " on"])
def test_any_other_value_is_refused_naming_port_sync(port_sync: str) -> None:
    values = "enabled, yes, on, true, disabled, no, off, false"
    message = f"PORT_SYNC must be one of {values}, got {port_sync!r}"
    with pytest.raises(SettingsError, match=f"^{re.escape(message)}$"):
        is_port_sync_enabled({"PORT_SYNC": port_sync})


def test_no_variable_set_but_the_ids_gives_todays_values() -> None:
    assert parse_port_sync_settings(IDS) == PortSyncSettings(
        gluetun_control_url="http://localhost:8000",
        poll_interval=timedelta(seconds=60),
        restart_min_interval=timedelta(seconds=300),
        uid=Uid(1000),
        gid=Gid(1001),
    )


def test_an_empty_variable_takes_the_domains_value() -> None:
    env = {
        **IDS,
        "GLUETUN_CONTROL_URL": "",
        "PORT_SYNC_POLL_SECONDS": "",
        "PORT_SYNC_RESTART_MIN_SECONDS": "",
    }
    assert parse_port_sync_settings(env) == parse_port_sync_settings(IDS)


def test_each_variable_overrides_the_domains_value() -> None:
    env = {
        **IDS,
        "GLUETUN_CONTROL_URL": "https://gluetun:9999/prefix",
        "PORT_SYNC_POLL_SECONDS": "5",
        "PORT_SYNC_RESTART_MIN_SECONDS": "30",
    }
    assert parse_port_sync_settings(env) == PortSyncSettings(
        gluetun_control_url="https://gluetun:9999/prefix",
        poll_interval=timedelta(seconds=5),
        restart_min_interval=timedelta(seconds=30),
        uid=Uid(1000),
        gid=Gid(1001),
    )


@pytest.mark.parametrize("name", list(IDS))
def test_port_sync_refuses_a_missing_id_naming_it(name: str) -> None:
    env = {key: setting for key, setting in IDS.items() if key != name}
    with pytest.raises(SettingsError, match=f"^{name} is required$"):
        parse_port_sync_settings(env)


@pytest.mark.parametrize("name", ["PORT_SYNC_POLL_SECONDS", "PORT_SYNC_RESTART_MIN_SECONDS"])
@pytest.mark.parametrize("setting", ["0", "-1", "1.5", "60s", "1_000", " 60", "١٠"])
def test_a_number_that_is_not_a_positive_integer_is_refused_naming_it(
    name: str, setting: str
) -> None:
    message = f"{name} must be a positive integer, got {setting!r}"
    with pytest.raises(SettingsError, match=f"^{re.escape(message)}$"):
        parse_port_sync_settings({name: setting})


@pytest.mark.parametrize(
    "url",
    [
        "localhost:8000",
        "ftp://gluetun:8000",
        "http://",
        "http:///v1",
        "http://[::1",
        "http://gluetun:99999",
        "http://gluetun:abc",
        "http://gluetun:0",
    ],
)
def test_a_malformed_url_is_refused_naming_it(url: str) -> None:
    message = f"GLUETUN_CONTROL_URL must be an http or https URL with a host, got {url!r}"
    with pytest.raises(SettingsError, match=f"^{re.escape(message)}$"):
        parse_port_sync_settings({"GLUETUN_CONTROL_URL": url})

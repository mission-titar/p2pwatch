"""The container's variables: the boot step's, required; port-sync's, with the domain's values."""

import re

import pytest

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


def test_the_boot_variables_give_the_boot_settings() -> None:
    assert parse_boot_settings(BOOT_ENV) == BootSettings(
        puid=1000, pgid=1001, ec_password="hunter2", api_password="s3cret"
    )


@pytest.mark.parametrize("name", list(BOOT_ENV))
@pytest.mark.parametrize("value", [None, ""])
def test_a_missing_or_empty_boot_variable_is_refused_naming_it(
    name: str, value: str | None
) -> None:
    env = {key: setting for key, setting in BOOT_ENV.items() if key != name}
    if value is not None:
        env[name] = value
    with pytest.raises(SettingsError, match=f"^{name} is required$"):
        parse_boot_settings(env)


def test_the_first_missing_boot_variable_is_the_one_named() -> None:
    with pytest.raises(SettingsError, match="^PUID is required$"):
        parse_boot_settings({})


@pytest.mark.parametrize("name", ["PUID", "PGID"])
@pytest.mark.parametrize("value", ["amule", "-1", "1 000", "1_000", "+1000", "١٠٠٠"])
def test_a_non_numeric_id_is_refused_naming_it(name: str, value: str) -> None:
    message = f"{name} must be a numeric id, got {value!r}"
    with pytest.raises(SettingsError, match=f"^{re.escape(message)}$"):
        parse_boot_settings({**BOOT_ENV, name: value})


@pytest.mark.parametrize("name", ["AMULE_EC_PASSWORD", "AMULE_API_PASSWORD"])
@pytest.mark.parametrize(
    "value", ["hunter2\n", "hun\tter2", "\rhunter2", "hunter2\x7f", "hunter2\x85"]
)
def test_a_password_with_a_control_character_is_refused_naming_it(name: str, value: str) -> None:
    with pytest.raises(SettingsError, match=f"^{name} must not contain a control character$"):
        parse_boot_settings({**BOOT_ENV, name: value})


def test_a_password_may_hold_spaces_and_non_ascii_letters() -> None:
    env = {**BOOT_ENV, "AMULE_API_PASSWORD": "mot de passé"}
    assert parse_boot_settings(env).api_password == "mot de passé"


@pytest.mark.parametrize("value", ["enabled", "yes", "on", "true", "On", "YES", "True"])
def test_gluetuns_true_values_turn_port_sync_on(value: str) -> None:
    assert is_port_sync_enabled({"PORT_SYNC": value}) is True


@pytest.mark.parametrize("value", ["disabled", "no", "off", "false", "Off", "FALSE", ""])
def test_gluetuns_false_values_and_an_empty_one_turn_it_off(value: str) -> None:
    assert is_port_sync_enabled({"PORT_SYNC": value}) is False


def test_an_unset_port_sync_is_off() -> None:
    assert is_port_sync_enabled({}) is False


@pytest.mark.parametrize("value", ["maybe", "1", "0", " on"])
def test_any_other_value_is_refused_naming_port_sync(value: str) -> None:
    values = "enabled, yes, on, true, disabled, no, off, false"
    message = f"PORT_SYNC must be one of {values}, got {value!r}"
    with pytest.raises(SettingsError, match=f"^{re.escape(message)}$"):
        is_port_sync_enabled({"PORT_SYNC": value})


def test_no_variable_set_gives_todays_values() -> None:
    assert parse_port_sync_settings({}) == PortSyncSettings(
        gluetun_control_url="http://localhost:8000", poll_seconds=60, restart_min_seconds=300
    )


def test_an_empty_variable_takes_the_domains_value() -> None:
    env = {
        "GLUETUN_CONTROL_URL": "",
        "PORT_SYNC_POLL_SECONDS": "",
        "PORT_SYNC_RESTART_MIN_SECONDS": "",
    }
    assert parse_port_sync_settings(env) == parse_port_sync_settings({})


def test_each_variable_overrides_the_domains_value() -> None:
    env = {
        "GLUETUN_CONTROL_URL": "https://gluetun:9999/prefix",
        "PORT_SYNC_POLL_SECONDS": "5",
        "PORT_SYNC_RESTART_MIN_SECONDS": "30",
    }
    assert parse_port_sync_settings(env) == PortSyncSettings(
        gluetun_control_url="https://gluetun:9999/prefix", poll_seconds=5, restart_min_seconds=30
    )


@pytest.mark.parametrize("name", ["PORT_SYNC_POLL_SECONDS", "PORT_SYNC_RESTART_MIN_SECONDS"])
@pytest.mark.parametrize("value", ["0", "-1", "1.5", "60s", "1_000", " 60", "١٠"])
def test_a_number_that_is_not_a_positive_integer_is_refused_naming_it(
    name: str, value: str
) -> None:
    message = f"{name} must be a positive integer, got {value!r}"
    with pytest.raises(SettingsError, match=f"^{re.escape(message)}$"):
        parse_port_sync_settings({name: value})


@pytest.mark.parametrize(
    "value",
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
def test_a_malformed_url_is_refused_naming_it(value: str) -> None:
    message = f"GLUETUN_CONTROL_URL must be an http or https URL with a host, got {value!r}"
    with pytest.raises(SettingsError, match=f"^{re.escape(message)}$"):
        parse_port_sync_settings({"GLUETUN_CONTROL_URL": value})

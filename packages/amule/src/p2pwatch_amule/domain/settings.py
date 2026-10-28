"""The container's variables: the boot step's, all required, and port-sync's.

A refused value raises `SettingsError` naming the variable.
"""

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlsplit

from p2pwatch_amule.domain.identifiers import Gid, Uid
from p2pwatch_amule.domain.settings_error import SettingsError

DEFAULT_GLUETUN_CONTROL_URL = "http://localhost:8000"
DEFAULT_PORT_SYNC_POLL_INTERVAL = timedelta(seconds=60)
DEFAULT_PORT_SYNC_RESTART_MIN_INTERVAL = timedelta(seconds=300)

# gluetun's own booleans (gosettings' parseBool), since PORT_SYNC receives VPN_PORT_FORWARDING.
_ON = ("enabled", "yes", "on", "true")
_OFF = ("disabled", "no", "off", "false")


@dataclass(frozen=True)
class BootSettings:
    uid: Uid
    gid: Gid
    ec_password: str
    api_password: str
    port_sync_enabled: bool


@dataclass(frozen=True)
class PortSyncSettings:
    gluetun_control_url: str
    poll_interval: timedelta
    restart_min_interval: timedelta
    uid: Uid
    gid: Gid


def parse_boot_settings(env: Mapping[str, str]) -> BootSettings:
    """Return the boot step's settings from `env`, refusing the first missing or invalid one,
    port-sync's included when it is on."""
    boot_settings = BootSettings(
        uid=_puid(env),
        gid=_pgid(env),
        ec_password=_password(env, "AMULE_EC_PASSWORD"),
        api_password=_password(env, "AMULE_API_PASSWORD"),
        port_sync_enabled=is_port_sync_enabled(env),
    )
    if boot_settings.port_sync_enabled:
        parse_port_sync_settings(env)
    return boot_settings


def is_port_sync_enabled(env: Mapping[str, str]) -> bool:
    """Return whether `PORT_SYNC` turns port-sync on; unset or empty is off."""
    port_sync = env.get("PORT_SYNC", "")
    if not port_sync:
        return False
    if port_sync.lower() in _ON:
        return True
    if port_sync.lower() in _OFF:
        return False
    raise SettingsError(f"PORT_SYNC must be one of {', '.join(_ON + _OFF)}, got {port_sync!r}")


def parse_port_sync_settings(env: Mapping[str, str]) -> PortSyncSettings:
    """Return port-sync's settings from `env`, an unset or empty variable taking the domain's
    value; the ids, amule.conf's owner, are required."""
    url = env.get("GLUETUN_CONTROL_URL") or DEFAULT_GLUETUN_CONTROL_URL
    try:
        parts = urlsplit(url)
        # .port raises on a non-numeric or out-of-range port, which urlsplit leaves unchecked.
        valid = parts.scheme in ("http", "https") and bool(parts.hostname) and parts.port != 0
    except ValueError:
        valid = False
    if not valid:
        raise SettingsError(
            f"GLUETUN_CONTROL_URL must be an http or https URL with a host, got {url!r}"
        )
    return PortSyncSettings(
        gluetun_control_url=url,
        poll_interval=_seconds(env, "PORT_SYNC_POLL_SECONDS", DEFAULT_PORT_SYNC_POLL_INTERVAL),
        restart_min_interval=_seconds(
            env, "PORT_SYNC_RESTART_MIN_SECONDS", DEFAULT_PORT_SYNC_RESTART_MIN_INTERVAL
        ),
        uid=_puid(env),
        gid=_pgid(env),
    )


def _required(env: Mapping[str, str], name: str) -> str:
    setting = env.get(name)
    if not setting:
        raise SettingsError(f"{name} is required")
    return setting


def _password(env: Mapping[str, str], name: str) -> str:
    password = _required(env, name)
    # Cc: the C0 and C1 controls and DEL, which no typed password holds.
    if any(unicodedata.category(char) == "Cc" for char in password):
        raise SettingsError(f"{name} must not contain a control character")
    return password


def _puid(env: Mapping[str, str]) -> Uid:
    return Uid(_numeric_id(env, "PUID"))


def _pgid(env: Mapping[str, str]) -> Gid:
    return Gid(_numeric_id(env, "PGID"))


def _numeric_id(env: Mapping[str, str], name: str) -> int:
    setting = _required(env, name)
    # isascii + isdigit: int() would also take "-1", "+1", "1_000", " 1" and non-ASCII digits.
    if not (setting.isascii() and setting.isdigit()):
        raise SettingsError(f"{name} must be a numeric id, got {setting!r}")
    return int(setting)


def _seconds(env: Mapping[str, str], name: str, default: timedelta) -> timedelta:
    setting = env.get(name)
    if not setting:
        return default
    # isascii + isdigit: int() would also take "-1", "+1", "1_000", " 1" and non-ASCII digits.
    if not (setting.isascii() and setting.isdigit()) or int(setting) == 0:
        raise SettingsError(f"{name} must be a positive integer, got {setting!r}")
    return timedelta(seconds=int(setting))

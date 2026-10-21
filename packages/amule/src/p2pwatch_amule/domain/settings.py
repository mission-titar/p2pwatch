"""Port-sync's environment variables: `is_port_sync_enabled` for the boot step,
`parse_port_sync_settings` for its settings.

A refused value raises `SettingsError` naming the variable, as the boot step's own variables do.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from p2pwatch_amule.domain.settings_error import SettingsError

DEFAULT_GLUETUN_CONTROL_URL = "http://localhost:8000"
DEFAULT_PORT_SYNC_POLL_SECONDS = 60
DEFAULT_PORT_SYNC_RESTART_MIN_SECONDS = 300

# gluetun's own booleans (gosettings' parseBool), since PORT_SYNC receives VPN_PORT_FORWARDING.
_ON = ("enabled", "yes", "on", "true")
_OFF = ("disabled", "no", "off", "false")


@dataclass(frozen=True)
class PortSyncSettings:
    gluetun_control_url: str
    poll_seconds: int
    restart_min_seconds: int


def is_port_sync_enabled(env: Mapping[str, str]) -> bool:
    """Return whether `PORT_SYNC` turns port-sync on; unset or empty is off."""
    value = env.get("PORT_SYNC", "")
    if not value:
        return False
    if value.lower() in _ON:
        return True
    if value.lower() in _OFF:
        return False
    raise SettingsError(f"PORT_SYNC must be one of {', '.join(_ON + _OFF)}, got {value!r}")


def parse_port_sync_settings(env: Mapping[str, str]) -> PortSyncSettings:
    """Return port-sync's settings from `env`, an unset or empty variable taking the domain's."""
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
        poll_seconds=_seconds(env, "PORT_SYNC_POLL_SECONDS", DEFAULT_PORT_SYNC_POLL_SECONDS),
        restart_min_seconds=_seconds(
            env, "PORT_SYNC_RESTART_MIN_SECONDS", DEFAULT_PORT_SYNC_RESTART_MIN_SECONDS
        ),
    )


def _seconds(env: Mapping[str, str], name: str, default: int) -> int:
    value = env.get(name)
    if not value:
        return default
    # isascii + isdigit: int() would also take "-1", "+1", "1_000", " 1" and non-ASCII digits.
    if not (value.isascii() and value.isdigit()) or int(value) == 0:
        raise SettingsError(f"{name} must be a positive integer, got {value!r}")
    return int(value)

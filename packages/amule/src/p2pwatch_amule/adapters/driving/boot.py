"""Entry point of the boot step: run once by the entrypoint, as root.

Before any change, exits naming the first variable missing or invalid, port-sync's included.
"""

import grp
import hashlib
import os
import pathlib
import pwd
import subprocess
import sys
import unicodedata
from collections.abc import Callable, Mapping

from p2pwatch_amule.domain.conf import (
    AMULE_CONF_PATH,
    CONFIG_DIR,
    INCOMING_DIR,
    TEMP_DIR,
    reconcile_conf,
)
from p2pwatch_amule.domain.settings import is_port_sync_enabled, parse_port_sync_settings

HOME_DIR = "/home/amule"
PORT_SYNC_DOWN_FILE = "/etc/services.d/port-sync/down"


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if not value:
        sys.exit(f"{name} is required")
    return value


def _password(env: Mapping[str, str], name: str) -> str:
    value = _required(env, name)
    # Cc: the C0 and C1 controls and DEL, which no typed password holds.
    if any(unicodedata.category(char) == "Cc" for char in value):
        sys.exit(f"{name} must not contain a control character")
    return value


def _required_id(env: Mapping[str, str], name: str) -> int:
    value = _required(env, name)
    # isascii + isdigit: int() would also take "-1", "+1", "1_000", " 1" and non-ASCII digits.
    if not (value.isascii() and value.isdigit()):
        sys.exit(f"{name} must be a numeric id, got {value!r}")
    return int(value)


def _amule_account_missing(lookup: Callable[[str], object]) -> bool:
    try:
        lookup("amule")
    except KeyError:
        return True
    return False


def main(env: Mapping[str, str]) -> None:
    puid = _required_id(env, "PUID")
    pgid = _required_id(env, "PGID")
    ec_password = _password(env, "AMULE_EC_PASSWORD")
    api_password = _password(env, "AMULE_API_PASSWORD")
    port_sync_enabled = is_port_sync_enabled(env)
    if port_sync_enabled:
        parse_port_sync_settings(env)

    # -o tolerates a uid/gid a Debian system account already holds: PUID/PGID only have to match
    # the host's ownership of the bind mounts.
    if _amule_account_missing(grp.getgrnam):
        subprocess.run(["groupadd", "-o", "-g", str(pgid), "amule"], check=True)
    if _amule_account_missing(pwd.getpwnam):
        useradd = ["useradd", "-o", "-u", str(puid), "-g", str(pgid), "-M", "-d", HOME_DIR]
        subprocess.run([*useradd, "-s", "/usr/sbin/nologin", "amule"], check=True)

    # Not recursive: the mounts can hold hundreds of gigabytes of part files the operator owns.
    owned_directories = [HOME_DIR, CONFIG_DIR, INCOMING_DIR, TEMP_DIR]
    for directory in owned_directories:
        os.makedirs(directory, exist_ok=True)
    for directory in owned_directories:
        os.chown(directory, puid, pgid)

    try:
        with open(AMULE_CONF_PATH) as handle:
            existing_conf: str | None = handle.read()
    except OSError:
        existing_conf = None
    # ECPassword is read as-is (only the GUI hashes what you type): the file holds the digest.
    digest = hashlib.md5(ec_password.encode()).hexdigest()
    with open(AMULE_CONF_PATH, "w") as handle:
        handle.write(reconcile_conf(existing_conf, digest))
    os.chown(AMULE_CONF_PATH, puid, pgid)
    os.chmod(AMULE_CONF_PATH, 0o600)

    # A non-loopback BindAddress needs an admin password or amuleapi refuses to start. Run as
    # amule so amuleapi-passwords (0600) lands with the ownership amuled's amuleapi expects.
    subprocess.run(
        ["amuleapi", f"--config-dir={CONFIG_DIR}", f"--set-admin-pass={api_password}"],
        user=puid,
        group=pgid,
        # Empty, not omitted: an omitted list keeps root's supplementary groups, group 0 included.
        extra_groups=[],
        env={**env, "HOME": HOME_DIR},
        check=True,
    )

    # s6's own way to keep a service down: its run script never starts.
    if port_sync_enabled:
        pathlib.Path(PORT_SYNC_DOWN_FILE).unlink(missing_ok=True)
    else:
        pathlib.Path(PORT_SYNC_DOWN_FILE).touch()

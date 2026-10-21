"""Entry point of the boot step: run once by the entrypoint, as root.

Before any change, refuses the first variable missing or invalid, port-sync's included.
"""

import grp
import hashlib
import os
import pwd
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from p2pwatch_amule.domain.conf import reconcile_conf
from p2pwatch_amule.domain.settings import (
    is_port_sync_enabled,
    parse_boot_settings,
    parse_port_sync_settings,
)


def _amule_account_missing(lookup: Callable[[str], object]) -> bool:
    try:
        lookup("amule")
    except KeyError:
        return True
    return False


def main(
    env: Mapping[str, str],
    *,
    home_directory: Path,
    config_directory: Path,
    incoming_directory: Path,
    temporary_directory: Path,
    amule_conf_path: Path,
    port_sync_down_file: Path,
) -> None:
    boot_settings = parse_boot_settings(env)
    puid, pgid = boot_settings.puid, boot_settings.pgid
    port_sync_enabled = is_port_sync_enabled(env)
    if port_sync_enabled:
        parse_port_sync_settings(env)

    # -o tolerates a uid/gid a Debian system account already holds: PUID/PGID only have to match
    # the host's ownership of the bind mounts.
    if _amule_account_missing(grp.getgrnam):
        subprocess.run(["groupadd", "-o", "-g", str(pgid), "amule"], check=True)
    if _amule_account_missing(pwd.getpwnam):
        useradd = [
            "useradd",
            "-o",
            "-u",
            str(puid),
            "-g",
            str(pgid),
            "-M",
            "-d",
            str(home_directory),
        ]
        subprocess.run([*useradd, "-s", "/usr/sbin/nologin", "amule"], check=True)

    # Not recursive: the mounts can hold hundreds of gigabytes of part files the operator owns.
    owned_directories = [home_directory, config_directory, incoming_directory, temporary_directory]
    for directory in owned_directories:
        os.makedirs(directory, exist_ok=True)
    for directory in owned_directories:
        os.chown(directory, puid, pgid)

    try:
        with open(amule_conf_path) as handle:
            existing_conf: str | None = handle.read()
    except OSError:
        existing_conf = None
    # ECPassword is read as-is (only the GUI hashes what you type): the file holds the digest.
    digest = hashlib.md5(boot_settings.ec_password.encode()).hexdigest()
    with open(amule_conf_path, "w") as handle:
        handle.write(reconcile_conf(existing_conf, digest))
    os.chown(amule_conf_path, puid, pgid)
    os.chmod(amule_conf_path, 0o600)

    # A non-loopback BindAddress needs an admin password or amuleapi refuses to start. Run as
    # amule so amuleapi-passwords (0600) lands with the ownership amuled's amuleapi expects.
    subprocess.run(
        [
            "amuleapi",
            f"--config-dir={config_directory}",
            f"--set-admin-pass={boot_settings.api_password}",
        ],
        user=puid,
        group=pgid,
        # Empty, not omitted: an omitted list keeps root's supplementary groups, group 0 included.
        extra_groups=[],
        env={**env, "HOME": str(home_directory)},
        check=True,
    )

    # s6's own way to keep a service down: its run script never starts.
    if port_sync_enabled:
        port_sync_down_file.unlink(missing_ok=True)
    else:
        port_sync_down_file.touch()

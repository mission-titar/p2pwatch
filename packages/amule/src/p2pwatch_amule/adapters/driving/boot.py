"""Entry point of the boot step: run once by the entrypoint, as root.

The booter first, which refuses the first variable missing or invalid before any change.
"""

import hashlib
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

from p2pwatch_amule.domain.conf import reconcile_conf
from p2pwatch_amule.domain.settings import is_port_sync_enabled, parse_boot_settings
from p2pwatch_amule.ports.driving.container_booter import ContainerBooter


def main(
    env: Mapping[str, str],
    *,
    container_booter: ContainerBooter,
    home_directory: Path,
    config_directory: Path,
    amule_conf_path: Path,
    port_sync_down_file: Path,
) -> None:
    container_booter.boot_container(env)
    # Already accepted by the booter.
    boot_settings = parse_boot_settings(env)
    puid, pgid = boot_settings.puid, boot_settings.pgid
    port_sync_enabled = is_port_sync_enabled(env)

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

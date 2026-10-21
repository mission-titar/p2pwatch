"""Entry point of the boot step: run once by the entrypoint, as root.

The booter first, which refuses the first variable missing or invalid before any change.
"""

from collections.abc import Mapping
from pathlib import Path

from p2pwatch_amule.domain.settings import is_port_sync_enabled
from p2pwatch_amule.ports.driving.container_booter import ContainerBooter


def main(
    env: Mapping[str, str],
    *,
    container_booter: ContainerBooter,
    port_sync_down_file: Path,
) -> None:
    container_booter.boot_container(env)

    # s6's own way to keep a service down: its run script never starts.
    if is_port_sync_enabled(env):
        port_sync_down_file.unlink(missing_ok=True)
    else:
        port_sync_down_file.touch()

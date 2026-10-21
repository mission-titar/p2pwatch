"""Boots the aMule container: refuses its variables first, then prepares the account."""

from collections.abc import Mapping

from p2pwatch_amule.domain.settings import (
    is_port_sync_enabled,
    parse_boot_settings,
    parse_port_sync_settings,
)
from p2pwatch_amule.ports.driven.account_manager import AccountManager
from p2pwatch_amule.ports.driving.container_booter import ContainerBooter


class BootContainer(ContainerBooter):
    """Parses every variable, port-sync's included, before the first change."""

    def __init__(self, *, account_manager: AccountManager) -> None:
        self._account_manager = account_manager

    def boot_container(self, env: Mapping[str, str]) -> None:
        boot_settings = parse_boot_settings(env)
        if is_port_sync_enabled(env):
            parse_port_sync_settings(env)
        self._account_manager.find_or_create_amule_account(boot_settings.puid, boot_settings.pgid)

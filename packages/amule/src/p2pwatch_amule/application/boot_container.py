"""Boots the aMule container: refuses its variables, then the account, directories and conf."""

from collections.abc import Mapping

from p2pwatch_amule.domain.conf import ec_password_digest, reconcile_conf
from p2pwatch_amule.domain.settings import (
    is_port_sync_enabled,
    parse_boot_settings,
    parse_port_sync_settings,
)
from p2pwatch_amule.ports.driven.account_manager import AccountManager
from p2pwatch_amule.ports.driven.amule_conf import AmuleConfReader, AmuleConfWriter
from p2pwatch_amule.ports.driven.amuled_directory_preparer import AmuledDirectoryPreparer
from p2pwatch_amule.ports.driving.container_booter import ContainerBooter


class BootContainer(ContainerBooter):
    """Parses every variable, port-sync's included, before the first change."""

    def __init__(
        self,
        *,
        account_manager: AccountManager,
        amuled_directory_preparer: AmuledDirectoryPreparer,
        amule_conf_reader: AmuleConfReader,
        amule_conf_writer: AmuleConfWriter,
    ) -> None:
        self._account_manager = account_manager
        self._amuled_directory_preparer = amuled_directory_preparer
        self._amule_conf_reader = amule_conf_reader
        self._amule_conf_writer = amule_conf_writer

    def boot_container(self, env: Mapping[str, str]) -> None:
        boot_settings = parse_boot_settings(env)
        if is_port_sync_enabled(env):
            parse_port_sync_settings(env)
        self._account_manager.find_or_create_amule_account(boot_settings.puid, boot_settings.pgid)
        self._amuled_directory_preparer.prepare_amuled_directories(
            boot_settings.puid, boot_settings.pgid
        )
        conf = reconcile_conf(
            self._amule_conf_reader.read_amule_conf(),
            ec_password_digest(boot_settings.ec_password),
        )
        self._amule_conf_writer.write_amule_conf(conf, boot_settings.puid, boot_settings.pgid)

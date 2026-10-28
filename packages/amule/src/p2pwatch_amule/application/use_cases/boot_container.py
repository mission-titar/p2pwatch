"""Boots the aMule container from its settings: each step, port-sync's state last."""

from p2pwatch_amule.application.ports.driven.account_provisioner import AccountProvisioner
from p2pwatch_amule.application.ports.driven.admin_password_setter import AdminPasswordSetter
from p2pwatch_amule.application.ports.driven.amule_conf_reader import AmuleConfReader
from p2pwatch_amule.application.ports.driven.amule_conf_writer import AmuleConfWriter
from p2pwatch_amule.application.ports.driven.amuled_directory_preparer import (
    AmuledDirectoryPreparer,
)
from p2pwatch_amule.application.ports.driven.service_supervisor import ServiceSupervisor
from p2pwatch_amule.application.ports.driving.container_booter import ContainerBooter
from p2pwatch_amule.domain.conf import ec_password_digest, reconcile_conf
from p2pwatch_amule.domain.settings import BootSettings


class BootContainer(ContainerBooter):
    """Prepares the container from ``boot_settings``, which hold every variable refused first."""

    def __init__(
        self,
        *,
        boot_settings: BootSettings,
        account_provisioner: AccountProvisioner,
        amuled_directory_preparer: AmuledDirectoryPreparer,
        amule_conf_reader: AmuleConfReader,
        amule_conf_writer: AmuleConfWriter,
        admin_password_setter: AdminPasswordSetter,
        service_supervisor: ServiceSupervisor,
    ) -> None:
        self._boot_settings = boot_settings
        self._account_provisioner = account_provisioner
        self._amuled_directory_preparer = amuled_directory_preparer
        self._amule_conf_reader = amule_conf_reader
        self._amule_conf_writer = amule_conf_writer
        self._admin_password_setter = admin_password_setter
        self._service_supervisor = service_supervisor

    def boot_container(self) -> None:
        boot_settings = self._boot_settings
        self._account_provisioner.find_or_create_amule_account(boot_settings.uid, boot_settings.gid)
        self._amuled_directory_preparer.prepare_amuled_directories(
            boot_settings.uid, boot_settings.gid
        )
        conf = reconcile_conf(
            self._amule_conf_reader.read_amule_conf(),
            ec_password_digest(boot_settings.ec_password),
        )
        self._amule_conf_writer.set_amule_conf(conf, boot_settings.uid, boot_settings.gid)
        self._admin_password_setter.set_admin_password(
            boot_settings.api_password, boot_settings.uid, boot_settings.gid
        )
        if boot_settings.port_sync_enabled:
            self._service_supervisor.enable_port_sync()
        else:
            self._service_supervisor.disable_port_sync()

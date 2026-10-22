"""The boot's composition: parses the container's variables, then assembles and runs the boot."""

from collections.abc import Mapping

from p2pwatch_amule.application.ports.driven.account_provisioner import AccountProvisioner
from p2pwatch_amule.application.ports.driven.admin_password_setter import AdminPasswordSetter
from p2pwatch_amule.application.ports.driven.amule_conf_reader import AmuleConfReader
from p2pwatch_amule.application.ports.driven.amule_conf_writer import AmuleConfWriter
from p2pwatch_amule.application.ports.driven.amuled_directory_preparer import (
    AmuledDirectoryPreparer,
)
from p2pwatch_amule.application.ports.driven.service_supervisor import ServiceSupervisor
from p2pwatch_amule.application.ports.driving.container_booter import ContainerBooter
from p2pwatch_amule.application.use_cases.boot_container import BootContainer
from p2pwatch_amule.domain.settings import parse_boot_settings


class BootComposition(ContainerBooter):
    """Parses the boot settings from ``env`` at each boot, then runs ``BootContainer`` on them."""

    def __init__(
        self,
        *,
        env: Mapping[str, str],
        account_provisioner: AccountProvisioner,
        amuled_directory_preparer: AmuledDirectoryPreparer,
        amule_conf_reader: AmuleConfReader,
        amule_conf_writer: AmuleConfWriter,
        admin_password_setter: AdminPasswordSetter,
        service_supervisor: ServiceSupervisor,
    ) -> None:
        self._env = env
        self._account_provisioner = account_provisioner
        self._amuled_directory_preparer = amuled_directory_preparer
        self._amule_conf_reader = amule_conf_reader
        self._amule_conf_writer = amule_conf_writer
        self._admin_password_setter = admin_password_setter
        self._service_supervisor = service_supervisor

    def boot_container(self) -> None:
        BootContainer(
            boot_settings=parse_boot_settings(self._env),
            account_provisioner=self._account_provisioner,
            amuled_directory_preparer=self._amuled_directory_preparer,
            amule_conf_reader=self._amule_conf_reader,
            amule_conf_writer=self._amule_conf_writer,
            admin_password_setter=self._admin_password_setter,
            service_supervisor=self._service_supervisor,
        ).boot_container()

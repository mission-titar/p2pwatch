"""The promise of the ``AmuleConfReader`` and ``AmuleConfWriter`` pair."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pytest

from p2pwatch_amule.application.ports.driven.amule_conf_reader import AmuleConfReader
from p2pwatch_amule.application.ports.driven.amule_conf_writer import AmuleConfWriter
from p2pwatch_amule.domain.identifiers import Gid, Uid


@dataclass(kw_only=True, frozen=True)
class AmuleConfPorts:
    """The pair's two ports, which one store implements."""

    writer: AmuleConfWriter
    reader: AmuleConfReader


class AmuleConfStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def amule_conf_ports(self) -> AmuleConfPorts:
        """The ports of a store holding no amule.conf yet."""

    @pytest.fixture
    @abstractmethod
    def unreadable_amule_conf_ports(self) -> AmuleConfPorts:
        """The ports of a store whose amule.conf exists but cannot be read."""

    def test_no_amule_conf_is_read_before_one_is_set(
        self, amule_conf_ports: AmuleConfPorts
    ) -> None:
        assert amule_conf_ports.reader.read_amule_conf() is None

    def test_a_set_amule_conf_is_read_back(self, amule_conf_ports: AmuleConfPorts) -> None:
        amule_conf_ports.writer.set_amule_conf(
            "[eMule]\nMaxUpload=42\n", uid=Uid(1000), gid=Gid(1001)
        )
        assert amule_conf_ports.reader.read_amule_conf() == "[eMule]\nMaxUpload=42\n"

    def test_a_second_amule_conf_replaces_the_first(self, amule_conf_ports: AmuleConfPorts) -> None:
        amule_conf_ports.writer.set_amule_conf(
            "[eMule]\nMaxUpload=42\n", uid=Uid(1000), gid=Gid(1001)
        )
        amule_conf_ports.writer.set_amule_conf(
            "[eMule]\nMaxUpload=7\n", uid=Uid(1000), gid=Gid(1001)
        )
        assert amule_conf_ports.reader.read_amule_conf() == "[eMule]\nMaxUpload=7\n"

    def test_an_amule_conf_that_cannot_be_read_raises_os_error(
        self, unreadable_amule_conf_ports: AmuleConfPorts
    ) -> None:
        with pytest.raises(OSError):
            unreadable_amule_conf_ports.reader.read_amule_conf()

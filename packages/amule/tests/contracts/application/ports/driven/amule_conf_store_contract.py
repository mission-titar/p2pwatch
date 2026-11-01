"""The promise of the ``AmuleConfReader`` and ``AmuleConfWriter`` pair."""

from abc import ABC, abstractmethod

import pytest

from p2pwatch_amule.application.ports.driven.amule_conf_reader import AmuleConfReader
from p2pwatch_amule.application.ports.driven.amule_conf_writer import AmuleConfWriter
from p2pwatch_amule.domain.identifiers import Gid, Uid


class AmuleConfStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def writer(self) -> AmuleConfWriter:
        """The writer of a store holding no amule.conf yet."""

    @pytest.fixture
    @abstractmethod
    def reader(self) -> AmuleConfReader:
        """The reader of the writer's store."""

    @pytest.fixture
    @abstractmethod
    def unreadable_reader(self) -> AmuleConfReader:
        """The reader of a store whose amule.conf exists but cannot be read."""

    def test_no_amule_conf_is_read_before_one_is_set(self, reader: AmuleConfReader) -> None:
        assert reader.read_amule_conf() is None

    def test_a_set_amule_conf_is_read_back(
        self, *, writer: AmuleConfWriter, reader: AmuleConfReader
    ) -> None:
        writer.set_amule_conf("[eMule]\nMaxUpload=42\n", uid=Uid(1000), gid=Gid(1001))
        assert reader.read_amule_conf() == "[eMule]\nMaxUpload=42\n"

    def test_a_second_amule_conf_replaces_the_first(
        self, *, writer: AmuleConfWriter, reader: AmuleConfReader
    ) -> None:
        writer.set_amule_conf("[eMule]\nMaxUpload=42\n", uid=Uid(1000), gid=Gid(1001))
        writer.set_amule_conf("[eMule]\nMaxUpload=7\n", uid=Uid(1000), gid=Gid(1001))
        assert reader.read_amule_conf() == "[eMule]\nMaxUpload=7\n"

    def test_an_amule_conf_that_cannot_be_read_raises_os_error(
        self, unreadable_reader: AmuleConfReader
    ) -> None:
        with pytest.raises(OSError):
            unreadable_reader.read_amule_conf()

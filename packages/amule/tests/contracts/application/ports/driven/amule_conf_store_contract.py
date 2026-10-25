"""The promise of the ``AmuleConfReader`` and ``AmuleConfWriter`` pair."""

from abc import ABC, abstractmethod
from typing import Protocol

import pytest


class AmuleConfStore(Protocol):
    """Both ports of the pair, which one store implements."""

    def read_amule_conf(self) -> str | None: ...

    def set_amule_conf(self, conf: str, uid: int, gid: int) -> None: ...


class AmuleConfStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def amule_conf_store(self) -> AmuleConfStore:
        """A store holding no amule.conf yet."""

    @pytest.fixture
    @abstractmethod
    def unreadable_amule_conf_store(self) -> AmuleConfStore:
        """A store whose amule.conf exists but cannot be read."""

    def test_no_amule_conf_is_read_before_one_is_set(
        self, amule_conf_store: AmuleConfStore
    ) -> None:
        assert amule_conf_store.read_amule_conf() is None

    def test_a_set_amule_conf_is_read_back(self, amule_conf_store: AmuleConfStore) -> None:
        amule_conf_store.set_amule_conf("[eMule]\nMaxUpload=42\n", 1000, 1001)
        assert amule_conf_store.read_amule_conf() == "[eMule]\nMaxUpload=42\n"

    def test_a_second_amule_conf_replaces_the_first(self, amule_conf_store: AmuleConfStore) -> None:
        amule_conf_store.set_amule_conf("[eMule]\nMaxUpload=42\n", 1000, 1001)
        amule_conf_store.set_amule_conf("[eMule]\nMaxUpload=7\n", 1000, 1001)
        assert amule_conf_store.read_amule_conf() == "[eMule]\nMaxUpload=7\n"

    def test_an_amule_conf_that_cannot_be_read_raises_os_error(
        self, unreadable_amule_conf_store: AmuleConfStore
    ) -> None:
        with pytest.raises(OSError):
            unreadable_amule_conf_store.read_amule_conf()

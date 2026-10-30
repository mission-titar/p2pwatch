"""PosixAmuleConfStore: amule.conf read as text, replaced whole, private to its given owner."""

import stat
from pathlib import Path

import pytest

from p2pwatch_amule.adapters.driven.posix_amule_conf_store import PosixAmuleConfStore
from p2pwatch_amule.domain.identifiers import Gid, Uid
from tests.contracts.application.ports.driven.amule_conf_store_contract import (
    AmuleConfPorts,
    AmuleConfStoreContract,
)
from tests.fakes.adapters.driven.fake_ownership import FakeOwnership


def _amule_conf_store(amule_conf_path: Path, *, ownership: FakeOwnership) -> PosixAmuleConfStore:
    return PosixAmuleConfStore(amule_conf_path=amule_conf_path, change_owner=ownership.change_owner)


class TestPosixAmuleConfStore(AmuleConfStoreContract):
    @pytest.fixture
    def amule_conf_store(self, tmp_path: Path) -> PosixAmuleConfStore:
        return _amule_conf_store(tmp_path / "amule.conf", ownership=FakeOwnership())

    @pytest.fixture
    def unreadable_amule_conf_store(self, tmp_path: Path) -> PosixAmuleConfStore:
        # A directory: IsADirectoryError, an OSError even as root.
        (tmp_path / "amule.conf").mkdir()
        return _amule_conf_store(tmp_path / "amule.conf", ownership=FakeOwnership())

    @pytest.fixture
    def amule_conf_ports(self, amule_conf_store: PosixAmuleConfStore) -> AmuleConfPorts:
        return AmuleConfPorts(writer=amule_conf_store, reader=amule_conf_store)

    @pytest.fixture
    def unreadable_amule_conf_ports(
        self, unreadable_amule_conf_store: PosixAmuleConfStore
    ) -> AmuleConfPorts:
        return AmuleConfPorts(
            writer=unreadable_amule_conf_store, reader=unreadable_amule_conf_store
        )


def test_the_written_conf_is_owned_and_private(tmp_path: Path) -> None:
    amule_conf_path = tmp_path / "amule.conf"
    amule_conf_path.write_text("[eMule]\nMaxUpload=42\n")
    amule_conf_path.chmod(0o644)
    ownership = FakeOwnership()

    _amule_conf_store(amule_conf_path, ownership=ownership).set_amule_conf(
        "[eMule]\nMaxUpload=7\n", uid=Uid(1000), gid=Gid(1001)
    )

    assert amule_conf_path.read_text() == "[eMule]\nMaxUpload=7\n"
    assert ownership.chowns == [(tmp_path / "amule.conf.tmp", Uid(1000), Gid(1001))]
    assert stat.S_IMODE(amule_conf_path.stat().st_mode) == 0o600
    assert list(tmp_path.iterdir()) == [amule_conf_path]


def test_the_previous_conf_is_replaced_not_truncated(tmp_path: Path) -> None:
    amule_conf_path = tmp_path / "amule.conf"
    amule_conf_path.write_text("[eMule]\nMaxUpload=42\n")

    with amule_conf_path.open() as previous_conf:
        _amule_conf_store(amule_conf_path, ownership=FakeOwnership()).set_amule_conf(
            "[eMule]\n", uid=Uid(1000), gid=Gid(1001)
        )

        assert previous_conf.read() == "[eMule]\nMaxUpload=42\n"


def test_a_leftover_temporary_file_lends_the_conf_none_of_its_mode(tmp_path: Path) -> None:
    amule_conf_path = tmp_path / "amule.conf"
    (tmp_path / "amule.conf.tmp").write_text("[eMule]\nMaxUpload=42\n")
    (tmp_path / "amule.conf.tmp").chmod(0o644)

    _amule_conf_store(amule_conf_path, ownership=FakeOwnership()).set_amule_conf(
        "[eMule]\n", uid=Uid(1000), gid=Gid(1001)
    )

    assert amule_conf_path.read_text() == "[eMule]\n"
    assert stat.S_IMODE(amule_conf_path.stat().st_mode) == 0o600


def test_a_failed_write_leaves_the_previous_conf_and_no_temporary_file(tmp_path: Path) -> None:
    amule_conf_path = tmp_path / "amule.conf"
    amule_conf_path.write_text("[eMule]\nMaxUpload=42\n")
    ownership = FakeOwnership()
    ownership.error = PermissionError("chown refused")

    with pytest.raises(PermissionError):
        _amule_conf_store(amule_conf_path, ownership=ownership).set_amule_conf(
            "[eMule]\n", uid=Uid(1000), gid=Gid(1001)
        )

    assert amule_conf_path.read_text() == "[eMule]\nMaxUpload=42\n"
    assert list(tmp_path.iterdir()) == [amule_conf_path]

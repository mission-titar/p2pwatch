"""PosixAmuleConf: amule.conf read as text, replaced whole, private to the owner it is given."""

import stat
from pathlib import Path

import pytest

from p2pwatch_amule.adapters.driven.posix_amule_conf import PosixAmuleConf
from tests.fakes import FakeOwnership


def _amule_conf(amule_conf_path: Path, ownership: FakeOwnership) -> PosixAmuleConf:
    return PosixAmuleConf(amule_conf_path=amule_conf_path, change_owner=ownership.change_owner)


def test_an_absent_conf_reads_as_none(tmp_path: Path) -> None:
    amule_conf = _amule_conf(tmp_path / "amule.conf", FakeOwnership())

    assert amule_conf.read_amule_conf() is None


def test_an_existing_conf_reads_as_its_text(tmp_path: Path) -> None:
    amule_conf_path = tmp_path / "amule.conf"
    amule_conf_path.write_text("[eMule]\nMaxUpload=42\n")
    amule_conf = _amule_conf(amule_conf_path, FakeOwnership())

    assert amule_conf.read_amule_conf() == "[eMule]\nMaxUpload=42\n"


def test_the_written_conf_is_owned_and_private(tmp_path: Path) -> None:
    amule_conf_path = tmp_path / "amule.conf"
    amule_conf_path.write_text("[eMule]\nMaxUpload=42\n")
    amule_conf_path.chmod(0o644)
    ownership = FakeOwnership()

    _amule_conf(amule_conf_path, ownership).write_amule_conf("[eMule]\nMaxUpload=7\n", 1000, 1001)

    assert amule_conf_path.read_text() == "[eMule]\nMaxUpload=7\n"
    assert ownership.chowns == [(tmp_path / "amule.conf.tmp", 1000, 1001)]
    assert stat.S_IMODE(amule_conf_path.stat().st_mode) == 0o600
    assert list(tmp_path.iterdir()) == [amule_conf_path]


def test_the_previous_conf_is_replaced_not_truncated(tmp_path: Path) -> None:
    amule_conf_path = tmp_path / "amule.conf"
    amule_conf_path.write_text("[eMule]\nMaxUpload=42\n")

    with amule_conf_path.open() as previous_conf:
        _amule_conf(amule_conf_path, FakeOwnership()).write_amule_conf("[eMule]\n", 1000, 1001)

        assert previous_conf.read() == "[eMule]\nMaxUpload=42\n"


def test_a_leftover_temporary_file_lends_the_conf_none_of_its_mode(tmp_path: Path) -> None:
    amule_conf_path = tmp_path / "amule.conf"
    (tmp_path / "amule.conf.tmp").write_text("[eMule]\nMaxUpload=42\n")
    (tmp_path / "amule.conf.tmp").chmod(0o644)

    _amule_conf(amule_conf_path, FakeOwnership()).write_amule_conf("[eMule]\n", 1000, 1001)

    assert amule_conf_path.read_text() == "[eMule]\n"
    assert stat.S_IMODE(amule_conf_path.stat().st_mode) == 0o600


def test_a_failed_write_leaves_the_previous_conf_and_no_temporary_file(tmp_path: Path) -> None:
    amule_conf_path = tmp_path / "amule.conf"
    amule_conf_path.write_text("[eMule]\nMaxUpload=42\n")
    ownership = FakeOwnership()
    ownership.error = PermissionError("chown refused")

    with pytest.raises(PermissionError):
        _amule_conf(amule_conf_path, ownership).write_amule_conf("[eMule]\n", 1000, 1001)

    assert amule_conf_path.read_text() == "[eMule]\nMaxUpload=42\n"
    assert list(tmp_path.iterdir()) == [amule_conf_path]

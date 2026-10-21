"""PosixAmuleConf: amule.conf read as text, replaced whole, private to the owner it is given."""

import stat
from pathlib import Path

from p2pwatch_amule.adapters.driven.posix_amule_conf import PosixAmuleConf


class FakeOwnership:
    """Records each chown with the text the file held: the gate cannot chown to another uid."""

    def __init__(self) -> None:
        self.chowned_files: list[tuple[str, int, int]] = []

    def change_owner(self, path: Path, uid: int, gid: int) -> None:
        self.chowned_files.append((path.read_text(), uid, gid))


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
    assert ownership.chowned_files == [("[eMule]\nMaxUpload=7\n", 1000, 1001)]
    assert stat.S_IMODE(amule_conf_path.stat().st_mode) == 0o600
    assert list(tmp_path.iterdir()) == [amule_conf_path]


def test_the_previous_conf_is_replaced_not_truncated(tmp_path: Path) -> None:
    amule_conf_path = tmp_path / "amule.conf"
    amule_conf_path.write_text("[eMule]\nMaxUpload=42\n")

    with amule_conf_path.open() as previous_conf:
        _amule_conf(amule_conf_path, FakeOwnership()).write_amule_conf("[eMule]\n", 1000, 1001)

        assert previous_conf.read() == "[eMule]\nMaxUpload=42\n"

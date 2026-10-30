import os
from pathlib import Path
from typing import Protocol

from p2pwatch_amule.application.ports.driven.amule_conf_reader import AmuleConfReader
from p2pwatch_amule.application.ports.driven.amule_conf_writer import AmuleConfWriter
from p2pwatch_amule.domain.identifiers import Gid, Uid


class OwnerChanger(Protocol):
    def __call__(self, *, path: Path, uid: Uid, gid: Gid) -> None: ...


class PosixAmuleConfStore(AmuleConfReader, AmuleConfWriter):
    """amule.conf at the path it is given, chowned through ``change_owner``."""

    def __init__(self, *, amule_conf_path: Path, change_owner: OwnerChanger) -> None:
        self._amule_conf_path = amule_conf_path
        self._change_owner = change_owner

    def read_amule_conf(self) -> str | None:
        try:
            return self._amule_conf_path.read_text()
        except FileNotFoundError:
            return None

    def set_amule_conf(self, conf: str, *, uid: Uid, gid: Gid) -> None:
        # Replaced, not rewritten in place: a failed write must not leave amuled a truncated file.
        temporary_path = self._amule_conf_path.with_name(self._amule_conf_path.name + ".tmp")
        # Created afresh: the 0600 applies only on creation, a leftover's mode would carry over.
        temporary_path.unlink(missing_ok=True)
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            with open(os.open(temporary_path, flags, 0o600), "w") as handle:
                handle.write(conf)
            self._change_owner(path=temporary_path, uid=uid, gid=gid)
            os.replace(temporary_path, self._amule_conf_path)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise

import subprocess
from pathlib import Path
from typing import Literal, Protocol

from p2pwatch_amule.application.ports.driven.account_provisioner import AccountProvisioner
from p2pwatch_amule.domain.identifiers import Gid, Uid


class CommandRunner(Protocol):
    def __call__(
        self, args: list[str], /, *, check: bool, text: Literal[True]
    ) -> subprocess.CompletedProcess[str]: ...


class AccountFinder(Protocol):
    def __call__(self, name: str, /) -> object: ...


class PosixAccountProvisioner(AccountProvisioner):
    """``groupadd`` and ``useradd``, each run only when its lookup raises ``KeyError``."""

    def __init__(
        self,
        *,
        home_directory: Path,
        run_command: CommandRunner,
        find_group: AccountFinder,
        find_user: AccountFinder,
    ) -> None:
        self._home_directory = home_directory
        self._run_command = run_command
        self._find_group = find_group
        self._find_user = find_user

    def find_or_create_amule_account(self, uid: Uid, gid: Gid) -> None:
        # -o tolerates a uid/gid a Debian system account already holds: PUID/PGID only have to
        # match the host's ownership of the bind mounts.
        if _is_missing(self._find_group):
            self._run_command(["groupadd", "-o", "-g", str(gid), "amule"], check=True, text=True)
        if _is_missing(self._find_user):
            useradd = [
                "useradd",
                "-o",
                "-u",
                str(uid),
                "-g",
                str(gid),
                "-M",
                "-d",
                str(self._home_directory),
            ]
            self._run_command([*useradd, "-s", "/usr/sbin/nologin", "amule"], check=True, text=True)


def _is_missing(find: AccountFinder) -> bool:
    try:
        find("amule")
    except KeyError:
        return True
    return False

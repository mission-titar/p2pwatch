from collections.abc import Callable
from pathlib import Path

from p2pwatch_amule.application.ports.driven.account_manager import AccountProvisioner


class PosixAccountProvisioner(AccountProvisioner):
    """``groupadd`` and ``useradd``, each run only when its lookup raises ``KeyError``."""

    def __init__(
        self,
        *,
        home_directory: Path,
        run_command: Callable[..., object],
        find_group: Callable[[str], object],
        find_user: Callable[[str], object],
    ) -> None:
        self._home_directory = home_directory
        self._run_command = run_command
        self._find_group = find_group
        self._find_user = find_user

    def find_or_create_amule_account(self, uid: int, gid: int) -> None:
        # -o tolerates a uid/gid a Debian system account already holds: PUID/PGID only have to
        # match the host's ownership of the bind mounts.
        if _is_missing(self._find_group):
            self._run_command(["groupadd", "-o", "-g", str(gid), "amule"], check=True)
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
            self._run_command([*useradd, "-s", "/usr/sbin/nologin", "amule"], check=True)


def _is_missing(find: Callable[[str], object]) -> bool:
    try:
        find("amule")
    except KeyError:
        return True
    return False

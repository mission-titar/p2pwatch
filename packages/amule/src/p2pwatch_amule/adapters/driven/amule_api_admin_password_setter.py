import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from p2pwatch_amule.application.ports.driven.admin_password_setter import AdminPasswordSetter
from p2pwatch_amule.domain.identifiers import Gid, Uid


class AmuleApiAdminPasswordSetter(AdminPasswordSetter):
    """``amuleapi --set-admin-pass`` over the config directory, run through ``run_command``."""

    def __init__(
        self,
        *,
        config_directory: Path,
        home_directory: Path,
        env: Mapping[str, str],
        run_command: Callable[..., subprocess.CompletedProcess[str]],
    ) -> None:
        self._config_directory = config_directory
        self._home_directory = home_directory
        self._env = env
        self._run_command = run_command

    def set_admin_password(self, api_password: str, uid: Uid, gid: Gid) -> None:
        # Run as amule so amuleapi-passwords (0600) lands owned as amuled's amuleapi expects.
        self._run_command(
            [
                "amuleapi",
                f"--config-dir={self._config_directory}",
                f"--set-admin-pass={api_password}",
            ],
            user=uid,
            group=gid,
            # Empty, not omitted: an omitted list keeps root's supplementary groups, 0 included.
            extra_groups=[],
            env={**self._env, "HOME": str(self._home_directory)},
            check=True,
            text=True,
        )

import subprocess
from typing import Any


class FakeCommandRunner:
    """Records each command run with its keyword arguments, each exiting ``exit_code`` with
    ``stderr``: the gate runs no s6, nor a command as another uid."""

    def __init__(self) -> None:
        self.commands: list[tuple[list[str], dict[str, Any]]] = []
        self.exit_code = 0
        self.stderr = ""

    def run_command(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.commands.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, self.exit_code, "", self.stderr)

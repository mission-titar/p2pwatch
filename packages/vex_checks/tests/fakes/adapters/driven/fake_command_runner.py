import subprocess
from typing import Any


class FakeCommandRunner:
    """Records each command run with its keyword arguments, each printing ``stdout``: the gate
    runs no grype."""

    def __init__(self) -> None:
        self.commands: list[tuple[list[str], dict[str, Any]]] = []
        self.stdout = ""

    def run_command(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.commands.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, self.stdout, "")

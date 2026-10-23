import subprocess
from typing import Any


class FakeCommandRunner:
    """Records each command run with its keyword arguments, each printing ``stdout`` and raising a
    non-zero ``returncode`` as ``check=True`` has ``subprocess.run`` do: the gate runs no grype."""

    def __init__(self) -> None:
        self.commands: list[tuple[list[str], dict[str, Any]]] = []
        self.stdout = ""
        self.returncode = 0

    def run_command(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.commands.append((argv, kwargs))
        completed = subprocess.CompletedProcess(argv, self.returncode, self.stdout, "")
        completed.check_returncode()
        return completed

"""``python -m vex_checks``: reads the process state and runs the command line on it."""

import os
import sys
from pathlib import Path

from vex_checks.composition.command_line import build_command_line

if __name__ == "__main__":  # pragma: no cover
    # Dev tooling, run from the workspace only: the repository is four parents up from here.
    repo_root = Path(__file__).resolve().parents[4]
    command_line = build_command_line(repo_root=repo_root, env=os.environ, cwd=Path.cwd())
    raise SystemExit(command_line.run(sys.argv[1:]))

"""``python -m vex_checks``: reads the process state and runs the command line on it."""

import os
import sys
from pathlib import Path

from vex_checks.composition.command_line import build_command_line

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(build_command_line(env=os.environ, cwd=Path.cwd()).run(sys.argv[1:]))

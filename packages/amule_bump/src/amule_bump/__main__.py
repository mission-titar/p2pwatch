"""``python -m amule_bump``: reads the process state and runs the command line on it."""

import os
import sys
import tempfile
from pathlib import Path

from amule_bump.composition.command_line import build_command_line

if __name__ == "__main__":  # pragma: no cover
    command_line = build_command_line(
        env=os.environ, cwd=Path.cwd(), temporary_directory=Path(tempfile.gettempdir())
    )
    raise SystemExit(command_line.run(sys.argv[1:]))

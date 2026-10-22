"""``python -m p2pwatch_amule``: reads the process state and runs the command line on it."""

import logging
import os
import sys

from p2pwatch_amule.composition.command_line import build_command_line

if __name__ == "__main__":  # pragma: no cover
    command_line = build_command_line(env=os.environ, root_logger=logging.getLogger())
    raise SystemExit(command_line.run(sys.argv[1:]))

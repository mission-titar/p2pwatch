"""``python -m p2pwatch_amule``: hands the entry points to the command line."""

import logging
import os
import sys
from collections.abc import Mapping, Sequence

from p2pwatch_amule.adapters.driving import boot, port_sync
from p2pwatch_amule.adapters.driving.cli.argparse_command_line import ArgparseCommandLine


def main(argv: Sequence[str], env: Mapping[str, str]) -> int:
    """Runs the subcommand ``argv`` names in the environment ``env``, returns its exit code."""
    command_line = ArgparseCommandLine(
        boot=lambda: boot.main(env),
        sync_listen_port=lambda: port_sync.main(env),
        root_logger=logging.getLogger(),
    )
    return command_line.run(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:], os.environ))

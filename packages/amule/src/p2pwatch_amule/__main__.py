"""``python -m p2pwatch_amule``: hands the entry points and their paths to the command line."""

import logging
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from p2pwatch_amule.adapters.driving import boot, port_sync
from p2pwatch_amule.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from p2pwatch_amule.domain.conf import INCOMING_DIR, TEMP_DIR

_HOME_DIR = Path("/home/amule")
_CONFIG_DIR = _HOME_DIR / ".aMule"
_AMULE_CONF_PATH = _CONFIG_DIR / "amule.conf"
_PORT_SYNC_DOWN_FILE = Path("/etc/services.d/port-sync/down")
_AMULED_SERVICE_DIR = Path("/etc/services.d/amuled")


def main(argv: Sequence[str], env: Mapping[str, str]) -> int:
    """Runs the subcommand ``argv`` names in the environment ``env``, returns its exit code."""
    command_line = ArgparseCommandLine(
        boot=lambda: boot.main(
            env,
            home_dir=_HOME_DIR,
            config_dir=_CONFIG_DIR,
            # The mount points are the directories reconcile_conf writes into amule.conf.
            incoming_dir=Path(INCOMING_DIR),
            temp_dir=Path(TEMP_DIR),
            amule_conf_path=_AMULE_CONF_PATH,
            port_sync_down_file=_PORT_SYNC_DOWN_FILE,
        ),
        sync_listen_port=lambda: port_sync.main(
            env, amule_conf_path=_AMULE_CONF_PATH, amuled_service_dir=_AMULED_SERVICE_DIR
        ),
        root_logger=logging.getLogger(),
    )
    return command_line.run(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:], os.environ))

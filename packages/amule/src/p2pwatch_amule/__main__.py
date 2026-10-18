"""``python -m p2pwatch_amule``: hands the entry points to the command line."""

from collections.abc import Sequence

from p2pwatch_amule.adapters.driving import boot, port_sync
from p2pwatch_amule.adapters.driving.cli.argparse_command_line import ArgparseCommandLine


def main(argv: Sequence[str] | None = None) -> None:
    """Runs the subcommand ``argv`` names (``sys.argv`` when ``None``)."""
    ArgparseCommandLine(boot=boot.main, sync_listen_port=port_sync.main).run(argv)


if __name__ == "__main__":  # pragma: no cover
    main()

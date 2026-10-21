"""``python -m vex_checks``: hands the checks to the command line."""

import functools
from collections.abc import Sequence

from vex_checks.adapters.driven.grype import SubprocessGrypeRunner
from vex_checks.adapters.driven.json_vex_reader import JsonVexReader
from vex_checks.adapters.driving import (
    check_claim_coverage,
    check_image_claims,
    check_source_claims,
    check_stale_claims,
)
from vex_checks.adapters.driving.cli.argparse_command_line import ArgparseCommandLine


def main(argv: Sequence[str] | None = None) -> int:
    """Runs the subcommand ``argv`` names (``sys.argv`` when ``None``), returns its exit code."""
    vex_reader = JsonVexReader()
    command_line = ArgparseCommandLine(
        check_image_claims=functools.partial(check_image_claims.main, vex_reader=vex_reader),
        check_stale_claims=functools.partial(
            check_stale_claims.main, runner=SubprocessGrypeRunner(), vex_reader=vex_reader
        ),
        check_source_claims=check_source_claims.main,
        check_claim_coverage=functools.partial(check_claim_coverage.main, vex_reader=vex_reader),
    )
    return command_line.run(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

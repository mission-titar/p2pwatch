"""Entry point ``python -m p2pwatch.merge``: safe-by-default merge CLI.

Aligned with ``composition/__main__.py`` (no ``[project.scripts]``:
invoked as ``python -m p2pwatch.merge``). ``main(argv) -> int`` returns an exit code:
``0`` = merge OK; ``2`` = usage/merge error (clear message on ``stderr``, never a bare
traceback); argparse itself returns ``2`` for a parsing error (mutually
exclusive/required group). No environment variable (repo doctrine, spec §6).

Safe-by-default (zero accidental loss, spec §6):
- ``--output`` new → created + merged; ``--output`` existing → refused UNLESS ``--force`` (append
  idempotent, never a truncate).
- ``--into <catalog>`` → dest = one of the source catalogs, which MUST be listed; the others are
  merged into it. Mutually exclusive with ``--output``; exactly one of the two is required.
- ``--force`` only makes sense with ``--output`` (rejected with ``--into``).
- a missing source catalog → ``MergeError`` BEFORE creating/opening the output (fail-fast).
"""

import argparse
import logging
import sys
from pathlib import Path

from p2pwatch.merge.errors import MergeError
from p2pwatch.merge.merger import merge_catalogs

_LOGGER = logging.getLogger("p2pwatch.merge")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="p2pwatch.merge",
        description="Merge N catalog.db into one (idempotent, append-only preserved).",
    )
    parser.add_argument(
        "source_catalogs",
        metavar="CATALOG",
        nargs="+",
        type=Path,
        help="1..N catalog.db files to merge (≥ 1).",
    )
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument(
        "--output",
        "-o",
        type=Path,
        help="FRESH output file (refused if it exists, unless --force).",
    )
    destination.add_argument(
        "--into",
        type=Path,
        help="Destination = one of the listed source catalogs (merged into it).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow an existing --output (idempotent append, never truncate).",
    )
    return parser.parse_args(argv)


def _resolve_destination(args: argparse.Namespace) -> tuple[Path, bool]:
    """Validates the safe-by-default rules and returns ``(output, output_is_source_catalog)``.

    Raises ``MergeError`` (clear message) BEFORE any opening/creation of the output:
    missing source catalogs, ``--force`` with ``--into``, existing ``--output`` without
    ``--force``, ``--into`` not listed in the source catalogs.
    """
    for source_catalog in args.source_catalogs:
        if not source_catalog.exists():
            raise MergeError(f"source catalog not found: {source_catalog}")

    if args.into is not None:
        if args.force:
            raise MergeError("--force makes no sense with --into")
        resolved_catalogs = {source_catalog.resolve() for source_catalog in args.source_catalogs}
        if args.into.resolve() not in resolved_catalogs:
            raise MergeError(f"--into must name a listed source catalog: {args.into}")
        return args.into, True

    # --output mode (the required group guarantees we have one OR the other; here it's --output).
    if args.output.exists() and not args.force:
        raise MergeError(f"output already exists: {args.output} (use --force to merge into it)")
    return args.output, False


def main(argv: list[str] | None = None) -> int:
    """CLI entry. ``0`` = OK, ``2`` = usage/merge error (clear message on stderr)."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        output, output_is_source_catalog = _resolve_destination(args)
        _LOGGER.info("merge → %s (%d source catalog(s))", output, len(args.source_catalogs))
        merge_catalogs(
            output, args.source_catalogs, output_is_source_catalog=output_is_source_catalog
        )
    except MergeError as error:
        print(f"Merge failed: {error}", file=sys.stderr, flush=True)
        return 2
    _LOGGER.info("merge done: %s", output)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

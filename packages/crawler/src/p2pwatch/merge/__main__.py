"""Entry point ``python -m p2pwatch.merge``: safe-by-default merge CLI.

Aligned with ``composition/__main__.py`` (no ``[project.scripts]``:
invoked as ``python -m p2pwatch.merge``). ``main(argv) -> int`` returns an exit code:
``0`` = merge OK; ``2`` = usage/merge error (clear message on ``stderr``, never a bare
traceback); argparse itself returns ``2`` for a parsing error (mutually
exclusive/required group). No environment variable (repo doctrine, spec §6).

Its safety rules are the use case ``MergeCatalogs``'s; this command line keeps one, no
``--force`` with ``--into``.
"""

import argparse
import logging
import sys
from pathlib import Path

from p2pwatch.adapters.pathlib_catalog_finder import PathlibCatalogFinder
from p2pwatch.adapters.persistence_sqlite.sqlite_catalog_copier import SqliteCatalogCopier
from p2pwatch.application.merge_catalogs import MergeCatalogs
from p2pwatch.ports.driving.catalog_merger import ListedSourceCatalog, MergeError, NewCatalog


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


def _destination(args: argparse.Namespace) -> NewCatalog | ListedSourceCatalog:
    """The destination the arguments name; ``--force`` with ``--into`` raises ``MergeError``."""
    if args.into is None:
        return NewCatalog(args.output, force=args.force)
    if args.force:
        raise MergeError("--force makes no sense with --into")
    return ListedSourceCatalog(args.into)


def main(argv: list[str] | None = None) -> int:
    """CLI entry. ``0`` = OK, ``2`` = usage/merge error (clear message on stderr)."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    catalog_merger = MergeCatalogs(PathlibCatalogFinder(), SqliteCatalogCopier())
    try:
        catalog_merger.merge_catalogs(args.source_catalogs, _destination(args))
    except MergeError as error:
        print(f"Merge failed: {error}", file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

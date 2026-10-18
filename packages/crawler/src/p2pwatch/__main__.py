"""``python -m p2pwatch``: builds the driving ports' implementations and runs the command line."""

import os
from collections.abc import Sequence

from p2pwatch.adapters.config.yaml_config_checker import YamlConfigChecker
from p2pwatch.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from p2pwatch.adapters.pathlib_catalog_finder import PathlibCatalogFinder
from p2pwatch.adapters.persistence_sqlite.sqlite_catalog_copier import SqliteCatalogCopier
from p2pwatch.application.merge_catalogs import MergeCatalogs
from p2pwatch.application.validate_config import ValidateConfig
from p2pwatch.composition.app import CrawlerApp

# 0.0.0.0: Docker cannot route a published port to the container's loopback. 8080, not 80: an
# unprivileged process cannot bind a port below 1024 under ``cap_drop: ALL``.
_WEBUI_ADDRESS = ("0.0.0.0", 8080)
# aMule's service in the direct variant, a network alias of its VPN sidecar in the vpn one.
_AMULE_API_ADDRESS = ("ed2k", 4711)


def main(argv: Sequence[str] | None = None) -> int:
    """Runs the subcommand ``argv`` names (``sys.argv`` when ``None``), returns its exit code."""
    command_line = ArgparseCommandLine(
        crawler_runner=CrawlerApp(
            webui_address=_WEBUI_ADDRESS, amule_api_address=_AMULE_API_ADDRESS, env=os.environ
        ),
        config_validator=ValidateConfig(YamlConfigChecker(os.environ)),
        catalog_merger=MergeCatalogs(PathlibCatalogFinder(), SqliteCatalogCopier()),
    )
    return command_line.run(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

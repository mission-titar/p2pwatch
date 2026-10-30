"""The command line of ``python -m p2pwatch``, on the driving ports' implementations."""

import logging
from collections.abc import Mapping
from pathlib import Path
from shutil import disk_usage

from p2pwatch.adapters.driven.config.filesystem_config_checker import FilesystemConfigChecker
from p2pwatch.adapters.driven.filesystem_catalog_finder import FilesystemCatalogFinder
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_catalog_copier import SqliteCatalogCopier
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    SqliteDatabaseOpener,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_pre_migration_copier import (
    SqlitePreMigrationCopier,
)
from p2pwatch.adapters.driven.stdlib_logger import StdlibLogger
from p2pwatch.adapters.driven.system_wall_clock import SystemWallClock
from p2pwatch.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from p2pwatch.application.use_cases.merge_catalogs import MergeCatalogs
from p2pwatch.application.use_cases.validate_config import ValidateConfig
from p2pwatch.composition.crawler_composition import CrawlerComposition

# 0.0.0.0: Docker cannot route a published port to the container's loopback. 8080, not 80: an
# unprivileged process cannot bind a port below 1024 under ``cap_drop: ALL``.
_WEBUI_ADDRESS = ("0.0.0.0", 8080)
# aMule's service in the direct variant, a network alias of its VPN sidecar in the vpn one.
_AMULE_API_ADDRESS = ("ed2k", 4711)


def build_command_line(
    *, env: Mapping[str, str], cwd: Path, root_logger: logging.Logger
) -> ArgparseCommandLine:
    """The command line run in the environment ``env`` and the directory ``cwd``, logging through
    ``root_logger``."""
    return ArgparseCommandLine(
        crawler_runner=CrawlerComposition(
            webui_address=_WEBUI_ADDRESS,
            amule_api_address=_AMULE_API_ADDRESS,
            env=env,
            root_logger=root_logger,
        ),
        config_validator=ValidateConfig(FilesystemConfigChecker(env)),
        catalog_merger=MergeCatalogs(
            FilesystemCatalogFinder(),
            catalog_copier=SqliteCatalogCopier(
                SqliteDatabaseOpener(
                    SqlitePreMigrationCopier(
                        SystemWallClock(), lambda directory: disk_usage(directory).free
                    )
                )
            ),
            logger=StdlibLogger(MergeCatalogs.__module__),
        ),
        root_logger=root_logger,
        cwd=cwd,
    )

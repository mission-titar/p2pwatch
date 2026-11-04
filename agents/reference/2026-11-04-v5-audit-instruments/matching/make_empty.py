"""An empty catalog at main's schema, to smoke-test run_main_migrated.py."""
import sys
from pathlib import Path
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_database_opener import SqliteDatabaseOpener


class _NoCopy:
    def ensure_copy(self, *args: object, **kwargs: object) -> None:
        return None


SqliteDatabaseOpener(_NoCopy()).open_catalog(Path(sys.argv[1])).close()  # type: ignore[arg-type]

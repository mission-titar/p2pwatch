"""Wrap probe: opens catalog.db then local.db of DATA_DIR as the crawler's composition does, logging with
timestamps, and prints the resident memory after; a monitor thread prints peak RSS and disk use.

wrap_open.py DATA_DIR
"""

import asyncio
import ctypes
import logging
import sys
import threading
from pathlib import Path
from shutil import disk_usage

from p2pwatch.adapters.driven.asyncio_monotonic_clock import AsyncioMonotonicClock
from p2pwatch.adapters.driven.glibc_memory_releaser import GlibcMemoryReleaser
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_database_opener import SqliteDatabaseOpener
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_pre_migration_copier import (
    SqlitePreMigrationCopier,
)
from p2pwatch.adapters.driven.system_wall_clock import SystemWallClock
from p2pwatch.adapters.driven.threading_ticker import ThreadingTicker

data = Path(sys.argv[1])
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("wrap")


def rss() -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) // 1024
    return -1


peak = {"rss": 0, "extra": 0, "free_drop": 0}
watched = Path(__import__("os").environ.get("WATCH_FREE", str(data)))
start_free = disk_usage(watched).free
stop = threading.Event()
start_size = sum(p.stat().st_size for p in data.iterdir() if p.is_file())


def monitor() -> None:
    while not stop.wait(0.5):
        peak["rss"] = max(peak["rss"], rss())
        size = sum(p.stat().st_size for p in data.iterdir() if p.is_file())
        peak["extra"] = max(peak["extra"], size - start_size)
        peak["free_drop"] = max(peak["free_drop"], start_free - disk_usage(watched).free)


async def main() -> None:
    ticker = ThreadingTicker(AsyncioMonotonicClock())
    free = lambda directory: disk_usage(directory).free  # noqa: E731
    opener = SqliteDatabaseOpener(
        SqlitePreMigrationCopier(SystemWallClock(), ticker=ticker, free_bytes=free),
        ticker=ticker,
        free_bytes=free,
        memory_releaser=GlibcMemoryReleaser(ctypes.CDLL(None)),
    )
    threading.Thread(target=monitor, daemon=True).start()
    catalog = opener.open_catalog(data / "catalog.db")
    local = opener.open_local(data / "local.db")
    stop.set()
    log.info("opened; VmRSS %d MB, peak %d MB, peak extra on disk %.2f GB (files), %.2f GB (free space drop)", rss(), peak["rss"], peak["extra"] / 1e9, peak["free_drop"] / 1e9)
    catalog.close()
    local.close()


asyncio.run(main())

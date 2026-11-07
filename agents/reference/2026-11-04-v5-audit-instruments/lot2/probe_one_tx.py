# Written for main before v5 lot 2 (fe691fbc): lot 2 changed _connect's arguments and deleted Migration.transactional.
"""Probe: copy, then every transactional catalog migration in one transaction, then VACUUM.

probe_one_tx.py DATA_DIR [catalog|local]
Prints JSON lines: phase timings, size samples (db, wal, partial copy), progress-handler gaps, memory.
"""

import ctypes
import json
import sqlite3
import sys
import threading
import time
from importlib import resources
from pathlib import Path

from p2pwatch.adapters.driven.persistence_sqlite.migration_scripts import load_scripts
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_database_opener import _connect
from p2pwatch.adapters.driven.persistence_sqlite.variants import remove_migration_sql_functions

data = Path(sys.argv[1])
which = "catalog"
path = data / f"{which}.db"
wal = Path(f"{path}-wal")
partial = data / f"{which}.db.pre-probe.partial"
t0 = time.monotonic()
phase = "start"
peak: dict[str, int] = {"extra": 0}
original_size = path.stat().st_size


def emit(**fields: object) -> None:
    print(json.dumps({"t": round(time.monotonic() - t0, 2), **fields}), flush=True)


def size(p: Path) -> int:
    try:
        return p.stat().st_size
    except FileNotFoundError:
        return 0


def rss() -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) // 1024
    return -1


stop = threading.Event()


def monitor() -> None:
    while not stop.wait(float(__import__("os").environ.get("PROBE_PERIOD", "2"))):
        db, w, c = size(path), size(wal), size(partial)
        extra = max(db - original_size, 0) + w + c
        if extra > peak["extra"]:
            peak.update(extra=extra, db=db, wal=w, copy=c, phase=phase)
        emit(sample=phase, db=db, wal=w, copy=c, rss_mb=rss())


gaps = {"last": time.monotonic(), "max": 0.0, "calls": 0}


def progress() -> int:
    now = time.monotonic()
    gaps["max"] = max(gaps["max"], now - gaps["last"])
    gaps["last"] = now
    gaps["calls"] += 1
    return 0


def run(name: str, fn) -> None:
    global phase
    phase = name
    gaps.update(last=time.monotonic(), max=0.0, calls=0)
    start = time.monotonic()
    fn()
    emit(phase=name, seconds=round(time.monotonic() - start, 1),
         progress_max_gap=round(gaps["max"], 2), progress_calls=gaps["calls"], rss_mb=rss())


threading.Thread(target=monitor, daemon=True).start()
connection = _connect(path)
connection.set_progress_handler(progress, 1_000_000)
version = connection.execute("PRAGMA user_version").fetchone()["user_version"]
scripts = load_scripts(resources.files("p2pwatch.adapters.driven.persistence_sqlite") / "migrations" / which)
pending = [m for m in scripts if m.version > version]
emit(version=version, pending=[m.version for m in pending], original=original_size, wal=size(wal))

if "--no-copy" not in sys.argv:
    run("copy", lambda: connection.execute("VACUUM INTO ?", (str(partial),)))
connection.execute("PRAGMA temp_store=FILE")


def block() -> None:
    connection.execute("BEGIN")
    for migration in (m for m in pending if m.transactional):
        start = time.monotonic()
        connection.executescript(migration.script)
        assert connection.in_transaction, migration.version
        emit(migration=migration.version, seconds=round(time.monotonic() - start, 1), wal=size(wal), db=size(path))
    connection.execute(f"PRAGMA user_version = {pending[-1].version}")
    connection.execute("COMMIT")


run("block", block)
connection.execute("PRAGMA cache_size = -2000")
connection.execute("PRAGMA secure_delete = OFF")
run("checkpoint", lambda: connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall())
emit(freelist=connection.execute("PRAGMA freelist_count").fetchone()["freelist_count"],
     pages=connection.execute("PRAGMA page_count").fetchone()["page_count"])
for migration in (m for m in pending if not m.transactional):
    run(f"outside-{migration.version}", lambda m=migration: connection.executescript(m.script))
remove_migration_sql_functions(connection)
emit(phase="before-trim", rss_mb=rss())
ctypes.CDLL("libc.so.6").malloc_trim(0)
emit(phase="after-trim", rss_mb=rss())
stop.set()
emit(peak=peak, final_db=size(path), final_wal=size(wal), copy=size(partial),
     integrity=connection.execute("PRAGMA quick_check").fetchone()["quick_check"],
     version=connection.execute("PRAGMA user_version").fetchone()["user_version"])

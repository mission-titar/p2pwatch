"""Memory after the crawler's database open, and what each candidate fix gives back.

Run in the p2pwatch image: python memprobe.py DATA_DIR STEPS [--tracemalloc]
STEPS is a comma list applied in order after open_catalog + open_local, each followed by a
measurement: gc, shrink, trim, reopen, cache0 (PRAGMA cache_size=0 then default), none.
Prints one JSON line per measurement.
"""

import ctypes
import gc
import json
import os
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from shutil import disk_usage

if "--tracemalloc" in sys.argv:
    tracemalloc.start(1)

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_database_opener import SqliteDatabaseOpener
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_pre_migration_copier import (
    SqlitePreMigrationCopier,
)
from p2pwatch.adapters.driven.system_wall_clock import SystemWallClock

libc = ctypes.CDLL("libc.so.6")
libsqlite = ctypes.CDLL("libsqlite3.so.0")
libsqlite.sqlite3_db_filename.restype = ctypes.c_char_p
libsqlite.sqlite3_db_filename.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
libsqlite.sqlite3_db_status.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.c_int]
libsqlite.sqlite3_status64.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_longlong), ctypes.POINTER(ctypes.c_longlong), ctypes.c_int]
libsqlite.sqlite3_memory_used.restype = ctypes.c_longlong
libc.malloc_trim.argtypes = [ctypes.c_size_t]


def handle(connection) -> int:
    # pysqlite_Connection: PyObject_HEAD then ``sqlite3 *db`` (CPython 3.13, Modules/_sqlite/connection.h).
    pointer = ctypes.c_void_p.from_address(id(connection) + 16).value
    assert libsqlite.sqlite3_db_filename(pointer, b"main"), "not a sqlite3 handle"
    return pointer


def db_status(connection, op: int) -> int:
    current, high = ctypes.c_int(), ctypes.c_int()
    libsqlite.sqlite3_db_status(handle(connection), op, ctypes.byref(current), ctypes.byref(high), 0)
    return current.value


def malloc_totals() -> dict:
    # malloc_stats() writes every arena to stderr; its last two lines are the totals.
    with tempfile.TemporaryFile(mode="w+") as sink:
        saved = os.dup(2)
        sys.stderr.flush()
        os.dup2(sink.fileno(), 2)
        libc.malloc_stats()
        os.dup2(saved, 2)
        os.close(saved)
        sink.seek(0)
        text = sink.read()
    totals = text.split("Total (incl. mmap):")[-1]
    system = int(totals.split("system bytes")[1].split("=")[1].split()[0])
    in_use = int(totals.split("in use bytes")[1].split("=")[1].split()[0])
    return {"malloc_system": system, "malloc_in_use": in_use, "arenas": text.count("Arena ")}


def rss() -> dict:
    fields = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(("VmRSS", "VmHWM", "RssAnon", "RssFile")):
            name, value = line.split(":")
            fields[name] = int(value.split()[0]) * 1024
    return fields


def measure(label: str, connections: dict) -> None:
    current, high = ctypes.c_longlong(), ctypes.c_longlong()
    libsqlite.sqlite3_status64(0, ctypes.byref(current), ctypes.byref(high), 0)
    record = {"step": label, "t": round(time.monotonic() - START, 1), **rss(), "sqlite_memory_used": current.value,
              "sqlite_memory_highwater": high.value, "py_blocks": sys.getallocatedblocks(), **malloc_totals()}
    for name, connection in connections.items():
        record[f"{name}_cache_used"] = db_status(connection, 1)  # SQLITE_DBSTATUS_CACHE_USED
        record[f"{name}_cache_size_pragma"] = connection.execute("PRAGMA cache_size").fetchone()["cache_size"]
        record[f"{name}_schema_used"] = db_status(connection, 2)
        record[f"{name}_stmt_used"] = db_status(connection, 3)
    if tracemalloc.is_tracing():
        traced, peak = tracemalloc.get_traced_memory()
        record["py_traced"], record["py_traced_peak"] = traced, peak
        top = tracemalloc.take_snapshot().statistics("filename")[:5]
        record["py_top"] = [(str(stat.traceback[0].filename).rsplit("/", 2)[-1], stat.size) for stat in top]
    print(json.dumps(record), flush=True)


START = time.monotonic()
data = Path(sys.argv[1])
steps = [step for step in sys.argv[2].split(",") if step]
opener = SqliteDatabaseOpener(SqlitePreMigrationCopier(SystemWallClock(), free_bytes=lambda d: disk_usage(d).free))
connections = {}
measure("start", connections)
connections["catalog"] = opener.open_catalog(data / "catalog.db")
connections["local"] = opener.open_local(data / "local.db")
measure("opened", connections)
for step in steps:
    if step == "gc":
        gc.collect()
    elif step == "shrink":
        for connection in connections.values():
            connection.execute("PRAGMA shrink_memory")
    elif step == "trim":
        libc.malloc_trim(0)
    elif step == "reopen":
        connections["catalog"].close()
        connections["catalog"] = opener.open_catalog(data / "catalog.db")
    elif step == "cache0":
        default = connections["catalog"].execute("PRAGMA cache_size").fetchone()["cache_size"]
        connections["catalog"].execute("PRAGMA cache_size = 0")
        connections["catalog"].execute(f"PRAGMA cache_size = {default}")
    measure(step, connections)

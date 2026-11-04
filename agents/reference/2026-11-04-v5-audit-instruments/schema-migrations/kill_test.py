"""Kills main's opener mid-migration (SIGKILL, as docker after its stop timeout), then restarts it.

Usage: python kill_test.py <bulk_dir> <work_dir> <python>
"""

import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

bulk, work, python = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
script = Path(__file__).with_name("open_once.py")

PHASES = [
    ("during-copy", "writing", 0.3),
    ("during-0007", "migration 7: applying", 20.0),
    ("during-0008", "migration 8: applying", 5.0),
    ("during-0009", "migration 9: applying", 0.7),
]


def listing(directory: Path) -> str:
    return ", ".join(f"{p.name}={p.stat().st_size}" for p in sorted(directory.iterdir()))


def state(directory: Path) -> str:
    connection = sqlite3.connect(f"file:{directory / 'catalog.db'}?mode=ro", uri=True)
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    check = connection.execute("PRAGMA quick_check").fetchone()[0]
    connection.close()
    return f"catalog user_version={version} quick_check={check}"


def run(directory: Path, trigger: str | None, delay: float) -> str:
    process = subprocess.Popen(
        [python, str(script), str(directory)], stderr=subprocess.PIPE, stdout=subprocess.PIPE,
        text=True,
    )
    log: list[str] = []
    killed = threading.Event()

    def reader() -> None:
        assert process.stderr is not None
        for line in process.stderr:
            log.append(line.rstrip().replace(str(directory) + "/", ""))
            if trigger and trigger in line and not killed.is_set():
                killed.set()
                threading.Timer(delay, lambda: process.send_signal(signal.SIGKILL)).start()

    thread = threading.Thread(target=reader)
    thread.start()
    process.wait()
    thread.join()
    out = process.stdout.read() if process.stdout else ""
    return f"exit={process.returncode} out={out.strip()!r}\n      " + "\n      ".join(log[-6:])


for name, trigger, delay in PHASES:
    directory = work / name
    shutil.rmtree(directory, ignore_errors=True)
    shutil.copytree(bulk, directory)
    print(f"== {name}: kill {delay}s after {trigger!r}")
    started = time.monotonic()
    print("   first run:", run(directory, trigger, delay))
    print(f"   after kill ({time.monotonic() - started:.1f}s): {state(directory)}")
    print("   files:", listing(directory))
    started = time.monotonic()
    print("   restart:", run(directory, None, 0))
    print(f"   after restart ({time.monotonic() - started:.1f}s): {state(directory)}")
    print("   files:", listing(directory))
    sys.stdout.flush()

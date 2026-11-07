"""Wrap probe: SIGKILLs wrap_open.py DELAY seconds after a log line containing TRIGGER, restarts it, reports.

wrap_kill.py DATA_DIR TRIGGER DELAY
"""

import signal
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

data, trigger, delay = Path(sys.argv[1]), sys.argv[2], float(sys.argv[3])
probe = Path(__file__).with_name("wrap_open.py")


def listing() -> str:
    return ", ".join(f"{p.name}={p.stat().st_size}" for p in sorted(data.iterdir()))


def version() -> str:
    connection = sqlite3.connect(f"file:{data / 'catalog.db'}?mode=ro", uri=True)
    try:
        return f"user_version={connection.execute('PRAGMA user_version').fetchone()[0]}"
    finally:
        connection.close()


process = subprocess.Popen([sys.executable, str(probe), str(data)], stderr=subprocess.STDOUT, stdout=subprocess.PIPE, text=True)
killed = threading.Event()


def kill_later() -> None:
    time.sleep(delay)
    process.send_signal(signal.SIGKILL)
    killed.set()


assert process.stdout is not None
for line in process.stdout:
    print("first:", line, end="", flush=True)
    if trigger in line and not killed.is_set():
        threading.Thread(target=kill_later, daemon=True).start()
process.wait()
print(f"killed={killed.is_set()} exit={process.returncode}; {version()}; {listing()}", flush=True)
second = subprocess.run([sys.executable, str(probe), str(data)], stderr=subprocess.STDOUT, stdout=subprocess.PIPE, text=True)
print("".join(f"second: {line}\n" for line in second.stdout.splitlines()), end="")
print(f"after restart exit={second.returncode}; {version()}; {listing()}", flush=True)

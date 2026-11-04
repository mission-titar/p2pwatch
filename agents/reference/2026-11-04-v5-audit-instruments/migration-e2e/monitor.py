"""Host monitor: every INTERVAL s, the container's memory, the files under DATA and the host's free space.

monitor.py CONTAINER DATA OUT INTERVAL
CSV: epoch, mem_bytes, data_total_bytes, df_avail_bytes, then name=size for each file.
"""

import os
import shutil
import subprocess
import sys
import time

UNITS = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "kB": 1000, "MB": 1000**2, "GB": 1000**3}


def memory(container: str) -> int:
    result = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", container],
        capture_output=True, text=True, check=False,
    )
    used = result.stdout.split("/")[0].strip()
    for unit in sorted(UNITS, key=len, reverse=True):
        if used.endswith(unit):
            try:
                return int(float(used[: -len(unit)]) * UNITS[unit])
            except ValueError:
                return -1
    return -1


def main() -> None:
    container, data, out, interval = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
    with open(out, "a", buffering=1) as sink:
        while True:
            sizes = {}
            for entry in os.scandir(data):
                try:
                    sizes[entry.name] = entry.stat().st_size
                except FileNotFoundError:
                    pass
            avail = shutil.disk_usage(data).free
            files = " ".join(f"{name}={size}" for name, size in sorted(sizes.items()))
            sink.write(f"{time.time():.1f},{memory(container)},{sum(sizes.values())},{avail},{files}\n")
            time.sleep(interval)


main()

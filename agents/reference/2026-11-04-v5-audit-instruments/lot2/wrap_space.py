"""Wrap probe: opens a copy of SEED_DIR on a private tmpfs of FACTOR times its catalog, as the image would
(SQLITE_TMPDIR on the same disk), then prints the catalog's version. No root: a user and mount namespace.

wrap_space.py SEED_DIR FACTOR
"""

import subprocess
import sys
from pathlib import Path

seed, factor = Path(sys.argv[1]).resolve(), float(sys.argv[2])
probe = Path(__file__).with_name("wrap_open.py")
size_kib = int((seed / "catalog.db").stat().st_size * factor / 1024)
inner = (
    "set -e; d=$(mktemp -d); mount -t tmpfs -o size=${SIZE}k tmpfs $d; cp $SEED/catalog.db $d/; set +e;"
    ' SQLITE_TMPDIR=$d $PY $PROBE $d; echo "exit $?";'
    ' $PY -c "import sqlite3,sys; c=sqlite3.connect(f\'file:{sys.argv[1]}/catalog.db?mode=ro\', uri=True);'
    ' print(\'user_version\', c.execute(\'PRAGMA user_version\').fetchone()[0])" $d'
)
env = {"SIZE": str(size_kib), "SEED": str(seed), "PY": sys.executable, "PROBE": str(probe), "PATH": "/usr/bin:/bin"}
print(f"tmpfs {size_kib / 1e6:.2f} GB, {factor} x the catalog", flush=True)
subprocess.run(["unshare", "-rm", "sh", "-c", inner], env=env, check=False)

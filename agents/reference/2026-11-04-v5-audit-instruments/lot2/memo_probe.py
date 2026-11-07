import ctypes, gc, sys
from importlib import resources
from pathlib import Path
from p2pwatch.adapters.driven.persistence_sqlite.migration_scripts import load_scripts
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_database_opener import _connect
def rss():
    return next(int(l.split()[1]) // 1024 for l in Path("/proc/self/status").read_text().splitlines() if l.startswith("VmRSS:"))
path = Path(sys.argv[1]); c = _connect(path)
scripts = load_scripts(resources.files("p2pwatch.adapters.driven.persistence_sqlite") / "migrations" / "catalog")
c.execute("BEGIN")
for m in scripts:
    if m.version > 5 and m.transactional: c.executescript(m.script)
c.execute("PRAGMA user_version = 15"); c.execute("COMMIT")
print("after block", rss(), "MB")
c.execute("PRAGMA cache_size=-2000"); ctypes.CDLL("libc.so.6").malloc_trim(0); print("trim, connection kept", rss(), "MB")
c.close(); gc.collect(); ctypes.CDLL("libc.so.6").malloc_trim(0); print("connection closed, trim", rss(), "MB")

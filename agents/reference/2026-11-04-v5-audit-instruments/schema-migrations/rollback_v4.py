"""Opens a restored pre-0006 copy with v4.1.0's code and reads its rows back."""
import sys
from pathlib import Path
from mulewatch.adapters.persistence_sqlite.connection import open_catalog, open_local
d = Path(sys.argv[1])
c = open_catalog(d / "catalog.db")
print("catalog", c.execute("PRAGMA user_version").fetchone()[0], c.execute("SELECT COUNT(*) FROM file_observations").fetchone()[0], c.execute("PRAGMA journal_mode").fetchone()[0])
l = open_local(d / "local.db")
print("local", l.execute("PRAGMA user_version").fetchone()[0], l.execute("SELECT * FROM node_runtime").fetchall())

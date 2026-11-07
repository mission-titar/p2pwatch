---
paths:
  - "packages/crawler/src/p2pwatch/application/use_cases/merge_catalogs.py"
  - "packages/crawler/src/p2pwatch/adapters/driven/persistence_sqlite/sqlite_catalog_copier.py"
  - "packages/crawler/src/p2pwatch/adapters/driven/persistence_sqlite/sqlite_database_opener.py"
  - "packages/crawler/src/p2pwatch/adapters/driving/cli/**"
---

# The catalog merge

- **The merge** (`python -m p2pwatch merge`) is never called by the crawl and writes only to its destination: a new file (`--output`), removed when no source entered it, or the source named by `--into`, which `SqliteDatabaseOpener.open_catalog` first migrates in place to the current schema. The one other file it writes is the destination's pre-migration copy, beside it, when a pending migration rewrites rows. It attaches each source read-only (`mode=ro`), so a source's bytes never change; beside a source in WAL mode SQLite creates a `-shm`, and an empty `-wal` when none was there, as any reader does.
- **The destination is held for the whole merge**: `open_catalog(..., exclusive=True)` takes SQLite's exclusive lock on `main` alone (a bare `locking_mode` would hold the attached sources too), without busy wait, so a destination another connection holds, a running node's, is refused before anything is written (`stop the node first`), and no crawler opens it meanwhile. Between the close and the reopen after a block of migrations nothing holds it: a connection that opens then makes the reopen refuse in the same words, the destination migrated, its copy kept.

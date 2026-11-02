---
paths:
  - "packages/crawler/src/p2pwatch/adapters/driven/persistence_sqlite/**"
  - "packages/crawler/tests/adapters/driven/persistence_sqlite/**"
---

# SQLite persistence

- Every row is read by column name through `NamedRow`, which refuses a read by index or by unpacking; the SQL console alone keeps positional rows, on a cursor of its own.
- `SqliteDatabaseOpener` opens every connection, the readers' included, and alone sets their row factory.
- It migrates both databases, keeping a pre-migration copy beside a database before a migration marked `-- migration: copy-before`, and never deleting one: mark a migration that rewrites rows.

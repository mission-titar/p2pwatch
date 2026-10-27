# Handoff: a copy before a migration that rewrites rows

Drafted by block 60 from the lot's block reports (#513, #514, #516, #517, #518) and its own, for the closing block 90
to correct with the holistic review.

## State

Tier Spec lot. Spec `agents/specs/2026-10-27-copy-before-migration.md` (reviewed by `migcopy-spec-review`, approved by the
operator 2026-10-27). It ships the backlog entry "A copy before a migration that rewrites rows", which block 90
deletes from `BACKLOG.md`, and drops from the entry "Every stamp an integer of microseconds since the epoch" its wait on
this lot (spec 8).

One stack cut from `main` at `cd307232`, which had not moved when block 60 was written (`git fetch`, 2026-10-27). Seven blocks with the closing one, as the spec planned; no split.
Block 20 took the mechanical exemption on its spec row (33 files).

| Block | Pull request | Branch |
|---|---|---|
| 10 | #513 | `refactor/sqlite-database-opener` |
| 20 | #514 | `refactor/tests-open-through-the-opener` |
| 30 | #516 | `feat/pre-migration-copy` |
| 40 | #517 | `feat/reuse-a-matching-copy` |
| 50 | #518 | `feat/mark-row-changing-migrations` |
| 60 | not opened at writing | `docs/pre-migration-copy` |
| 90 | the closing block's | `docs/pre-migration-copy-wrap` |

Not merged at writing. **No release follows this lot**: the v5 waits for a P2P network other than eD2k (operator,
2026-10-27). The lot changes what the image ships (the `main` image copies before a marked migration from block 50 on),
so the copy reaches the node only with the v5 release, or through a `main` image the operator chooses to run.

## What was built

- **The opener** (block 10, D8): `SqliteDatabaseOpener(pre_migration_copier)` in
  `adapters/driven/persistence_sqlite/sqlite_database_opener.py`, methods `open_catalog(path)` and `open_local(path)`,
  is the one way the code opens a database. Its private `_open` reads `connect`, `pending_migrations`, `ensure_copy`,
  `apply_migrations`, and closes the connection on any failure. `connection.py` keeps the independent pieces
  (`connect`, `load_scripts`, `pending_migrations`, `apply_migrations`). `PendingMigrations(current_version,
  migrations)` is built only by `pending_migrations`, so neither the copy nor the migrations can run before the
  version was read. The crawler's composition builds one opener for both databases (the config's `str` paths wrapped
  in `Path`); `build_command_line` builds one for `merge` and hands it to `SqliteCatalogCopier`'s constructor.
- **The old functions removed** (block 20): the tests open through
  `tests/support/adapters/driven/persistence_sqlite/sqlite_database_opener.py` (`open_catalog`, `open_local`,
  `database_opener()`), over a copier with a `FakeWallClock` and ample space.
- **The copy** (block 30, D2, D3, D4, D6): the directive `-- migration: copy-before`, exact first line, beside
  `-- migration: no-transaction` (`Migration.copy_before`); `SqlitePreMigrationCopier(wall_clock, free_bytes)` in
  `sqlite_pre_migration_copier.py`, method `ensure_copy(connection, path, pending)`: delete leftover `.partial` files
  and their journals, stop if the version is 0 or no pending migration is marked, check the space, `VACUUM INTO`
  `<file>.pre-<NNNN>.partial` from the opener's connection, then `os.link` to
  `<file>.pre-<NNNN>.<YYYY-MM-DD_HH-MM-SS>_UTC` and unlink the `.partial`; a taken name raises a `MigrationError`
  naming it. The need is the live pages plus the `-wal` for the copy, then the file plus the `-wal` for the
  migrations; short, `MigrationError("pre-migration copy of <path>: <need> bytes needed in <dir>, <free> free")`
  before any write. `free_bytes` is a `Callable[[Path], int]` the composition passes over `shutil.disk_usage`;
  `FakeFreeBytes` in `tests/fakes/adapters/driven/fake_free_bytes.py`. A new `tach.toml` edge from
  `persistence_sqlite` to the `WallClock` port. The word "runner" left `connection.py` and its tests.
- **The reuse** (block 40, D5): `database_digest.py`, a SHA-256 over the `user_version`, the sorted schema SQL and the
  sum modulo 2^256 of each row's SHA-256 of `repr((table_name, row))`, over every table `sqlite_schema` lists, read
  through SQLite so the `-wal` counts. Before copying, the copier digests the most recent
  `<file>.pre-<NNNN>.*_UTC` (`NNNN` the first pending version), opened read-only, and reuses it on equality; one that
  cannot be read matches nothing and is left alone. The open tests still in `test_connection.py` moved to the
  opener's.
- **The marks** (block 50, 4.1): catalog 0005, 0006, 0007, 0008, 0011 and local 0004, 0005, 0006, 0007, 0010, 0011
  carry the directive. `test_migration_directives.py` parses every shipped script with sqlfluff and requires the
  directive exactly when it holds a `DELETE`, an `UPDATE`, a `DROP TABLE`, an `INSERT ... SELECT` or an
  `ALTER TABLE ... DROP COLUMN`; sqlfluff joined the crawler's `dev` group. `AGENTS.md`: the Persistence row, the merge
  invariant (`SqliteDatabaseOpener.open_catalog`, the copy beside the destination), the clock invariant.
- **The documents** (block 60, spec 5): `docs/operate.md` gains "La copie d'avant migration" (when, its name, the
  reuse, the second copy after a return, when to delete one, which one to keep, how to restore) and its mentions in
  the update, the disk planning and `merge`; `docs/limits.md` gains the need in `data/` and the 2026-10-13 spike's
  table in place of the 2026-10-09 one; `docs/migration-4x.md` gains the copy in the backup warning, in "Ce qui
  change" and a restore from the copies in "Retour arrière"; `docs/troubleshooting-start.md` an entry for the space
  refusal; `docs/install.md` the space in its upgrade warning; `docs/contributing/architecture.md` the opener in
  place of "the runner" and the `copy-before` directive in the migration recipe.

## Evidence

Every block's `uv run poe check` exit 0 at its tip (crawler: 1635 passed at blocks 10 and 20, 1645 at 30, 1656 at 40,
1677 at 50; 100 % branch coverage; `_unit-coverage-check` clean). Block 60: `uv run poe check` and
`uv run poe docs-build` ("No issues found"); the strict build shown failing on a dead anchor first
(`RuntimeError: Aborted because --strict flag is set`).

Budgets against each parent: block 10, 272 lines and 10 files; block 20, 113 lines and 33 files (exemption); block
30, 364 and 12; block 40, 370 and 6; block 50, 285 and 18; block 60, 142 and 6.

Each criterion's test watched failing, from the block reports:

- 1, 2, 3, 4 (block 30): against an empty `ensure_copy`, `assert [] == ['catalog.db....00-00-00_UTC']` and
  `DID NOT RAISE MigrationError`; without the cleanup, `sqlite3.OperationalError: output file already exists`; with a
  bare `os.link`, `FileExistsError`.
- 5, 6, 7 (block 40): against block 30's copier, two copies where one was expected; against a reuse by name alone,
  one copy where two were expected; without the `sqlite3.Error` catch, `PersistenceError: file is not a database`.
- 8 (block 40): against a stub digest, `assert b'' != b''` for each of the six changes.
- 9 (block 30): `MigrationError: 0002_drop.sql: unknown directive '-- migration: copy-before'`.
- 10, 13, 14, 16 (block 50): before the marks, `assert [] == [...]` or `ValueError: not enough values to unpack`.
- 11, 12 (block 50): under a mutation of the copier (without the "marked" check, without the version 0 check).
- 15 (block 50): before the marks, the test lists the 11 unmarked scripts.

## Departures from the spec

- `PendingMigrations` gained `current_version` in block 30, with its reader, not in block 10 (vulture).
- 4.2's pieces and `older_catalog.py`'s chaining were done in block 10, not 30 (the lead's brief).
- Criteria 1 to 7 run on the copier with the opener's steps chained in the test: the opener's scripts are its own
  code, not a parameter (`AGENTS.md`).
- 4.2's step 3 reads only copies of the first pending version: one of another version cannot match, since the
  `user_version` is in the digest.
- Criterion 10's catalog leaves `file_observation_ranges` empty, which 0006 refuses to migrate.
- The docs (block 60) say which copy to keep as "the smallest number, the most recent if several", rather than the
  spec's "the earliest copy of an unfinished upgrade": after a return to the old release and a new try, the earliest
  `pre-0006` misses the rows the old release wrote since. The 4.x rollback restores the most recent `pre-0006`.
- `docs/limits.md`'s 2026-10-09 measurements (196 to 295 s on a 5.3 GB copy) were replaced by the 2026-10-13 spike's
  (502.5 s for the copy, 674.9 s for 0006 to 0010, on a 5.9 GB snapshot of the node's catalog): the spike is more
  recent, on the node's own catalog, and the earlier "three to five minutes" was more than twice too short.

## Pitfalls

- vulture matches names, not owners: a method sharing a module function's name keeps the function "used".
- pyrefly's index goes stale after a `sed` rewrite of imports: `git grep -w` is the check before deleting a symbol.
- A test that wants a non-empty `-wal` writes it from a second connection with `wal_autocheckpoint=0`.
- `VACUUM INTO` keeps `sqlite_stat1` and `sqlite_stat4`, so a database with `ANALYZE` statistics digests equal to its
  copy.
- From block 50 on, a test that opens an older database through the support opener leaves a copy in its `tmp_path`.
- In the docs, the zensical slug of "La copie d'avant migration" is `la-copie-davant-migration` (the apostrophe drops).

## Not validated

- **The node's first upgrade under this code** has not run: neither the copy of its 7.55 GB catalog, its duration, the
  space check against the node's disk, nor a digest on that catalog (spec 8, "Not in this lot").
- The integration suites run only in CI's `validate / gate`.

## Next

Block 90, the closing block: the holistic review's fixes, `BACKLOG.md` (this lot's entry deleted, the microseconds
entry's wait dropped), this handoff corrected (the fix-backs, cascaded rebases and runs they re-triggered counted).
No release proposal (above). Then the backlog, read before proposing.

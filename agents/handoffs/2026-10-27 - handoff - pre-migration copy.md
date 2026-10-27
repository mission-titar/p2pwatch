# Handoff: a copy before a migration that rewrites rows

Drafted by block 60 from the lot's block reports (#513, #514, #516, #517, #518) and its own, corrected by the closing
block 90 with the holistic review and block 80's report (#520).

## State

Tier Spec lot. Spec `agents/specs/2026-10-27-copy-before-migration.md` (reviewed by `migcopy-spec-review`, approved by the
operator 2026-10-27). It ships the backlog entry "A copy before a migration that rewrites rows", which block 90
deleted from `BACKLOG.md`, and dropped from the entry "Every stamp an integer of microseconds since the epoch" its wait
on this lot (spec 8). Nothing else changed in `BACKLOG.md`.

One stack cut from `main` at `cd307232`, which had not moved when block 90 was written (`git fetch`, 2026-10-27).
Eight blocks: the closing block split in two, block 80 for the code and block 90 for the documents, since together
they passed the 20-file bound (16 files, then 6). Block 20 took the mechanical exemption on its spec row (33 files).

| Block | Pull request | Branch |
|---|---|---|
| 10 | #513 | `refactor/sqlite-database-opener` |
| 20 | #514 | `refactor/tests-open-through-the-opener` |
| 30 | #516 | `feat/pre-migration-copy` |
| 40 | #517 | `feat/reuse-a-matching-copy` |
| 50 | #518 | `feat/mark-row-changing-migrations` |
| 60 | #519 | `docs/pre-migration-copy` |
| 80 | #520 | `fix/pre-migration-copy-review` |
| 90 | the closing block's | `docs/pre-migration-copy-wrap` |

Not merged at writing. **No release follows this lot**: the v5 waits for a P2P network other than eD2k (operator,
2026-10-27). The lot changes what the image ships (the `main` image copies before a marked migration from block 50 on),
so the copy reaches the node only with the v5 release, or through a `main` image the operator chooses to run.

## What was built

- **The opener** (block 10, D8): `SqliteDatabaseOpener(pre_migration_copier)` in
  `adapters/driven/persistence_sqlite/sqlite_database_opener.py`, methods `open_catalog(path)` and `open_local(path)`,
  is the one way the code migrates a database (`ThreadReadConnections` and the SQL console open both databases
  without migrating them). Its private `_open` reads `connect`, `pending_migrations`, `ensure_copy`,
  `apply_migrations`, and closes the connection on any failure. `connection.py` keeps the independent pieces
  (`connect`, `load_scripts`, `pending_migrations`, `apply_migrations`). `PendingMigrations(current_version,
  migrations)` is built by `pending_migrations` by convention, which the type makes visible: neither the copy nor the
  migrations can run before the version was read, as long as no other module builds one (no gate rule refuses it,
  operator 2026-10-27). The crawler's composition builds one opener for both databases (the config's `str` paths wrapped
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
- **The holistic review's code findings** (block 80): every `OSError` of the link becomes a `MigrationError` naming
  the final file; the candidate's read-only URI is `file:` plus the percent-quoted path, so a relative path from
  `crawler.yml` works; `test_migration_directives.py` also counts `INSERT OR REPLACE`, `REPLACE INTO` and an upsert's
  `DO UPDATE`, and ignores a trigger's body; `*.db.pre-*` in `.gitignore` and `.dockerignore`; the wording findings
  (below).
- **The holistic review's document findings** (block 90): the 4.x rollback without a backup restores only a database
  that has a `pre-0006` copy, one command per database, the rename before the removal of `-wal` and `-shm`;
  `troubleshooting-start.md`'s restart loop says it is slow after an upgrade and how to halt it; `AGENTS.md`,
  `architecture.md`, the spec's corrections (`(Corrected: ...)` markers) and this handoff.

## Evidence

Every block's `uv run poe check` exit 0 at its tip (crawler: 1635 passed at blocks 10 and 20, 1645 at 30, 1656 at 40,
1677 at 50; 100 % branch coverage; `_unit-coverage-check` clean). Block 60: `uv run poe check` and
`uv run poe docs-build` ("No issues found"); the strict build shown failing on a dead anchor first
(`RuntimeError: Aborted because --strict flag is set`).

Block 80: `uv run poe check` exit 0 (crawler: 1684 passed, 100 % coverage). Block 90: `uv run poe check` (crawler 1684 passed) and
`uv run poe docs-build`, both exit 0.

Budgets against each parent: block 10, 272 lines and 10 files; block 20, 113 lines and 33 files (exemption); block
30, 364 and 12; block 40, 370 and 6; block 50, 285 and 18; block 60, 142 and 6; block 80, 95 and 16; block 90,
49 and 6.

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
- Block 80's new tests: the three rewriting `INSERT`s, `assert [] == ['0001_script.sql']`; the trigger body,
  `assert ['0001_script.sql'] == []`; the refused link, `OSError: [Errno 36] File name too long`; the relative path,
  `ValueError: relative path can't be expressed as a file URI`. The quoting was shown needed by a mutation (a
  directory named `data #%?`).

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
- Block 80: one wording for every link failure, `pre-migration copy: <final> not created: <strerror>`, still naming
  the file. Its link-failure test relies on a 255-byte NAME_MAX (ext4, tmpfs, btrfs, overlayfs). `INSERT ... ON
  CONFLICT DO NOTHING` was added as a non-rewriting case.
- Block 90: the 4.x rollback renames the copy over the database before removing `-wal` and `-shm`, where the spec said
  remove then rename: a mistyped copy name then deletes nothing. The `ls` reads `*.pre-0006.*_UTC`, since a leftover
  `.partial` would sort after the dated copies.
- `docs/limits.md`'s 2026-10-09 measurements (196 to 295 s on a 5.3 GB copy) were replaced by the 2026-10-13 spike's
  (502.5 s for the copy, 674.9 s for 0006 to 0010, on a 5.9 GB snapshot of the node's catalog): the spike is more
  recent, on the node's own catalog, and the earlier "three to five minutes" was more than twice too short.

## The holistic review

`.reviews/copy-before-migration-holistic.md` (gitignored): MAJOR 1, MINOR 12, every finding fixed in the lot.

| Finding | Exit |
|---|---|
| MAJOR: the 4.x rollback without a backup deleted a `local.db` that had no copy | fixed, block 90 (`migration-4x.md`, `operate.md`) |
| Any `os.link` failure but a taken name escaped as a bare `OSError`, the copy deleted | fixed, block 80 |
| `INSERT OR REPLACE`, `REPLACE INTO` and the upsert's `DO UPDATE` passed the directive test unmarked | fixed, block 80 (test) and 90 (recipe); spec 4.1 extended and trigger bodies excluded by the operator, 2026-10-27, with a new accepted limit (spec 8) |
| `as_uri()` refused a relative database path on the reuse path | fixed, block 80 |
| The restart loop is slow after an upgrade, the docs said otherwise | fixed, block 90 (`troubleshooting-start.md`) |
| "Runner" survived | fixed, block 80 (code, scripts, tests) and 90 (`AGENTS.md`) |
| `PendingMigrations`' order claimed by the type | fixed, block 80 (docstring) and 90 (spec, handoff): a convention the type makes visible, no gate rule (operator, 2026-10-27) |
| `instant` for the formatted text; `FakeFreeBytes.free` without its unit | fixed, block 80 (`stamp`, `available_bytes`) |
| "the one way the code opens" a database | fixed, block 80 (docstring) and 90 (`AGENTS.md`, handoff): "migrates" |
| Two section references in lines the lot rewrote | fixed, block 80 |
| `*.db.pre-*` not ignored by git or Docker | fixed, block 80 |
| `test_open_local_runs_the_pre_migration_copier_before_migrating` promised an order it cannot see | fixed, block 80 (renamed) |
| `test_merge_copies_a_version_5_destination_and_no_source`'s second half could not fail | fixed, block 80 (renamed) |

Seen by block 80 outside the findings, not fixed: the other `spec §N` references in `connection.py`, older than the
lot, and `FakeFreeSpaceMeter.free`, also without its unit.

## Counts

Fix-backs: none. Cascaded rebases: none. Runs they re-triggered: none. No body called unreadable. The stack is not yet
rebased onto `main` for the merge, which had not moved.

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
- **The tag path**: no release follows, so `release.yml` has not published an image carrying this code. The copy
  reaches the node only with the v5 release, or through a `main` image the operator chooses to run.
- The integration suites run only in CI's `validate / gate`.

## Next

No release proposal: the v5 waits for a P2P network other than eD2k (operator, 2026-10-27). Then `BACKLOG.md`, read
before proposing: "Every stamp an integer of microseconds since the epoch" no longer waits for this lot.

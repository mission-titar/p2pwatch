# A copy before a migration that rewrites rows

Tier Spec. Discussed with the operator on 2026-10-27. Starts from section 9 of
`agents/specs/2026-10-13-append-only-source-points.md` and departs from it where the decisions say so.

How to read it: section 1 says the problem, section 2 what the operator will see, section 3 the choices and why.
Section 4 is the design for the blocks, with the identifiers. Sections 5 to 8 are the docs, the tests, the blocks
and the limits. The appendices hold the facts and the measurements.

## 1. The problem

The node runs 4.1.0. Its next upgrade, whatever release it is, rewrites both of its databases: several pending
migrations delete or rewrite rows (appendix A). A migration that fails rolls back. One that succeeds with a wrong
result leaves no way back unless the operator made a backup first. The docs ask for one, and that is a step an
operator can skip. The catalog's observations cannot be gathered again.

`BACKLOG.md` marks this as required before the next release. No release follows this lot: the v5 waits for a P2P
network other than eD2k (operator, 2026-10-27).

## 2. What the operator will see

- **A normal upgrade.** At the first start, before migrating, the crawler copies each database that a pending
  migration will rewrite. The copy sits beside it in `data/`, for example
  `catalog.db.pre-0006.2026-10-27_11-53-00_UTC`. One copy per database, however many migrations are pending. The
  node's upgrade from 4.1.0 leaves `catalog.db.pre-0006…` (about 7.5 GB) and `local.db.pre-0006…` (45 KB).
- **A migration that fails.** The crawler stops, Docker restarts it, and the migration fails again. The copy is made
  once: the next starts see that the database still matches it and reuse it.
- **A return to the old release, then a new try.** The old release writes new rows, so the database no longer matches
  the copy. The new try makes a second copy and keeps the first.
- **Not enough disk.** The crawler refuses to start before writing anything, and its log names the space needed and
  the space free. On the node, from version 5, the need is about 15.1 GB in `data/`.
- **`merge`.** A destination that `merge` migrates is copied the same way. Its sources are never copied.
- **Deleting copies.** p2pwatch never deletes one. The docs say when the operator may, and to keep, among an
  unfinished upgrade's copies, the one with the smallest number, the most recent if several. (Corrected: "the
  earliest copy" became this in block 60. After a return to the old release and a new try, the earliest `pre-0006`
  misses the rows the old release wrote since.)

## 3. Decisions

Each decision is the choice, then its reason.

**D1. Both databases.** The copy covers `catalog.db` and `local.db`, at the crawler's start and on `merge`'s
destination. *`local.db` holds the node's identity and its tracked downloads, and four of its pending migrations
change rows on the node. Its copy costs nothing (45 KB), and both databases are opened by the same code (operator).*

**D2. A migration declares that it rewrites rows.** Its first line is `-- migration: copy-before`. *The name follows
the existing `-- migration: no-transaction`, which also tells the code that applies the script what to do with it (operator).*

**D3. One copy per open, before the first pending migration.** It covers every pending migration. A new database is
not copied. *A copy per migration would multiply a 7.5 GB file for nothing: the first copy already holds everything
the later migrations change.*

**D4. The copy's name reads at a glance**: `<file>.pre-<NNNN>.<YYYY-MM-DD_HH-MM-SS>_UTC`, `NNNN` the first pending
version. *The dot keeps the version apart from the year, `_UTC` says the zone, and the seconds keep two copies of
`local.db`, made in an instant, from colliding (operator). The file's own name leads, since `merge` opens a
destination of any name.*

**D5. A copy is reused only when it matches the database's content.** *Reusing a copy because of its name alone, as
section 9 planned, would reuse a stale copy after a return to the old release (operator). SQLite offers no cheap proof
of identity, so the proof is a digest of the content, paid only on the rare paths (appendix B).*

**D6. The crawler refuses to copy when the disk is short, before writing anything.** *A copy that fills the disk
halfway leaves the node worse off than before.*

**D7. p2pwatch never deletes a copy.** *A backup that deletes itself works against its purpose: a wrong result from a
migration can surface weeks later (operator).* The one to keep until an upgrade succeeds is the copy with the smallest
number, the most recent if several: a larger number holds a half-migrated database. (Corrected: added in block 60, in
place of section 2's "earliest".)

**D8. Opening a database goes through an object the composition builds.** `SqliteDatabaseOpener` replaces the
functions `open_catalog` and `open_local`, and receives a `SqlitePreMigrationCopier` that makes the copies. *The copy
needs the time and the free space, which the persistence adapter may not read itself; the copier carries both, and
the opener carries the copier to the crawler and to `merge`. Two classes, one per responsibility: opening and
migrating, and keeping a copy to restore. Removing the old functions makes the copy impossible
to skip by design (operator, for the name: the callers want a connection, and copying is part of opening).*

**D9. `restart: unless-stopped` stays.** *It restarts the crawler after the dashboard's restart button, a reboot and a
crash. D5 already keeps the restart loop from piling up copies (operator).*

## 4. Design

### 4.1 The directive

- Exact first line, the same grammar as `-- migration: no-transaction` (`connection.py:118-124`). `Migration` gains
  `copy_before: bool` beside `transactional: bool`: the model allows both, and only the script reader takes one
  directive per script, since no script needs both today (the only `no-transaction` script, catalog 0009, changes no
  row). *The reader's grammar is a detail of how scripts are read, not a rule of what a migration is (operator).*
- Marked: catalog 0005, 0006, 0007, 0008, 0011; local 0004, 0005, 0006, 0007, 0010, 0011 (appendix A). Those the node
  already applied are marked too: `merge` can open an older catalog, and a node older than local version 5 can still
  upgrade (`docs/migration-1x.md`, `docs/migration-2x.md`).
- A unit test parses every shipped script with sqlfluff's parser (`Linter(dialect="sqlite").parse_string`), the one
  `poe sql-lint` already runs on them. A script holding a `delete_statement`, an `update_statement`, a
  `drop_table_statement`, an `insert_statement` that contains a `select_statement`, a `REPLACE` keyword or an upsert's
  `DO UPDATE`, or an `ALTER TABLE ... DROP COLUMN` must carry the directive, and one carrying it must hold one of them.
  A statement inside a `CREATE TRIGGER` body does not count: it does not run when the script creates the trigger.
  sqlfluff joins the crawler's `dev` group. (Corrected: `INSERT OR REPLACE`, `REPLACE INTO`, the upsert's `DO UPDATE`
  and the trigger bodies, from the holistic review, operator 2026-10-27; done in block 80.)
- *Why: a future script that forgets the directive then fails the gate, where a fixed list would not. A test over the
  parsed SQL rather than a sqlfluff rule: a custom rule needs a plugin package installed through an entry point, and a
  test sits higher than a lint rule in what enforces it. Parsed rather than a keyword scan: a keyword inside a string
  or a comment cannot fool it. The parse matches appendix A on every script (appendix B), but 0009, whose `VACUUM`
  sqlfluff does not parse and which already carries `-- noqa: PRS` for `poe sql-lint`.*

### 4.2 The steps of an open

The sequence of an open lives in one place, the opener's private method `_open(path, scripts)`, which
`open_catalog` and `open_local` call. It reads top to bottom, and nothing outside the opener calls its steps one by
one:

```python
connection = connect(path)                               # WAL, pragmas, SQL functions
pending = pending_migrations(connection, scripts)        # raises if the database is newer than the code
self._pre_migration_copier.ensure_copy(connection, path, pending)  # the steps below
apply_migrations(connection, pending)
```

`connection.py` keeps only independent pieces, each taking what it needs as parameters: configure a connection, load
the scripts, apply scripts. Its private `_open` goes, and with it the word "runner".

`pending_migrations(connection, scripts)` returns a `PendingMigrations(current_version, migrations)`, a frozen value
it builds after refusing a database newer than the code. `ensure_copy` and `apply_migrations` take it and nothing
else of the version, so a caller that builds it only through `pending_migrations` cannot run either before the
database's version was read. *The type makes the order visible, as `MonotonicInstant` does the clock's (operator).*
(Corrected: the order is a convention the type makes visible, not one the type carries: any module can build a
`PendingMigrations`, and no gate rule refuses it. Operator, 2026-10-27, from the holistic review.)

`SqlitePreMigrationCopier.ensure_copy` runs these steps, each only if the previous one did not end it; on return, a
pre-migration copy matching the database exists, or none was needed:

1. **Clean**: delete every leftover `<file>.pre-*.partial` and its `-journal`.
2. **Decide**: stop here if no pending migration is marked, wherever it sits, or if the version is 0.
3. **Reuse**: take the most recent `<file>.pre-<NNNN>.*_UTC` by name; if its digest equals the database's, stop here.
4. **Check the space** (4.5).
5. **Copy** with `VACUUM INTO` to `<file>.pre-<NNNN>.partial`, from the opener's own connection, outside any
   transaction, then link it to its final name (4.3).

*The order matters: a lookup that matched `.partial` would take a killed copy for the most recent one; a reused copy
must still clear a leftover; a space reading before the cleanup would count the leftover against the need.*

`older_catalog.py`'s builders, which build older databases for the tests, chain `connect`, `pending_migrations` and
`apply_migrations` themselves, as their `secure_delete` variant already does, `PendingMigrations` holding them to the
order: they start from version 0, which is never copied.

### 4.3 Writing the copy

- The name's instant is the `WallClock`'s, in UTC, to the second.
- The `.partial` is linked to the final name with `os.link`, then unlinked. A taken name raises `FileExistsError`,
  turned into a `MigrationError` naming the file, and the `.partial` is removed. *`os.rename` and `os.replace` would
  silently replace an existing file.* (Corrected: every `OSError` of the link becomes that `MigrationError`, a
  filesystem without hard links included, in block 80 from the holistic review.)
- A leftover must be deleted first: without its journal, `VACUUM INTO` fails on it with `file is not a database`;
  complete, with `output file already exists` (appendix B).

### 4.4 The digest

- It covers the `user_version`, the schema (`sqlite_schema`'s SQL, sorted) and every row of every table that
  `sqlite_schema` lists when the digest runs, SQLite's own tables included. No list of tables in the code, and nothing
  taken from the catalog being append-only: a table added by a future migration is covered without a line changed.
- It reads through SQLite (`SELECT`), never the files, so the committed rows still in the `-wal` count. Each row is
  hashed with its table's name; the hashes are added, so the rows' order does not matter. The candidate copy is opened
  read-only.
- A candidate that cannot be read (its open or its digest raises a `sqlite3.Error`) is a non-match: a new copy is made
  and that file is left alone.
- *Why a digest. In WAL mode the header's change counter does not move, a rolled-back transaction changes the
  `-wal`'s mtime, and `data_version` moves on a checkpoint that changed nothing. The database file's mtime and size
  move or stay regardless of content (a checkpoint, a `touch`, a `cp -a`). Counting rows is exact only for the
  append-only catalog, not for `local.db`. The digest's cost, about a minute of CPU per side on the catalog, is a lower
  bound (appendix B), paid only after a failure or a return to an old release.*

### 4.5 Free space

- Read through `free_bytes` on the database's directory. The need is:
  - for the copy: the live pages, `(page_count - freelist_count) * page_size`, plus the `-wal`;
  - for the migrations: the database file plus the `-wal`.
- Short: a `MigrationError` naming the need and the free space, nothing written.
- *The copy half counts the live pages because the file keeps its size after a migration drops rows (no
  `auto_vacuum`): if 0006 committed and 0007 failed, counting the file would ask for the whole catalog again for a
  small copy. The migrations half keeps the file's size; the 2026-10-13 spike measured copy plus migrations at 1.007
  times the catalog.*
- SQLite's temporary files are not counted: they go to Docker's disk, which `docs/limits.md` covers.

### 4.6 The opener and its wiring

- `SqliteDatabaseOpener(pre_migration_copier)` in `adapters/driven/persistence_sqlite/sqlite_database_opener.py`,
  methods `open_catalog(path)` and `open_local(path)`, each returning a `sqlite3.Connection` as today. The module
  functions are removed.
- `SqlitePreMigrationCopier(wall_clock, free_bytes)` in `sqlite_pre_migration_copier.py`, method
  `ensure_copy(connection, path, pending)`: the steps of 4.2, the name and the space check.
- `wall_clock` is the `WallClock` port: a new `tach.toml` edge from `persistence_sqlite` to
  `p2pwatch.application.ports.driven.wall_clock`.
- `free_bytes` is a `Callable[[Path], int]`; the composition passes `lambda directory: shutil.disk_usage(directory).free`.
  *Why it is passed in: a test must put the free space one byte short, and `AGENTS.md` forbids patching a module.
  Why it takes the directory: `merge` opens a destination anywhere, so the directory is known only at each open; a
  factory of meters built from it is the smell Seemann and van Deursen name ("Abusing Abstract Factories", chapter 6 of
  "Dependency Injection Principles, Practices, and Patterns"), whose remedy passes the runtime value as an argument.
  Why a `Callable` rather than `FreeSpaceMeter.free_bytes(directory)`: `AGENTS.md` asks for a driven port when the core
  needs it and a typed `Callable` inside an adapter, and here only the persistence adapter needs it. Reshaping the
  port would also have the `DownloadDecider` supply a directory it does not use today, its fakes and tests changed.*
- The crawler's composition builds `SqliteDatabaseOpener(SqlitePreMigrationCopier(wall_clock, free_bytes))` with its
  `SystemWallClock`, opens both databases and passes the connections to the stores as today. `build_command_line`
  builds one with a `SystemWallClock` for `merge` and passes the opener to `SqliteCatalogCopier`'s constructor.
- Modules: `connection.py` keeps its pieces (4.2); the digest goes in `database_digest.py`. All in the one
  `persistence_sqlite` tach module.
- Own tests: `test_sqlite_database_opener.py` (the open tests move there from `test_connection.py`),
  `test_sqlite_pre_migration_copier.py`, `test_database_digest.py`, each covering every branch of its module.
- Test support: `tests/support/adapters/driven/persistence_sqlite/sqlite_database_opener.py` gives `open_catalog(path)`
  and `open_local(path)` over an opener whose copier has a `FakeWallClock` and ample space, so a test that only needs an open
  database changes its import line only. `FakeFreeBytes`, in `tests/fakes/adapters/driven/fake_free_bytes.py`,
  returns the bytes its test gives it and keeps the directories it was asked about.
- Words: the code, its logs and the docs say "pre-migration copy", never a bare "copy", since `SqliteCatalogCopier`
  already copies catalogs for `merge`.

## 5. Documents

- `AGENTS.md`, in block 50, which turns the behaviour on: the Persistence row names the opener and the pre-migration
  copy; the merge invariant (`:50`) allows the copy beside the destination and names
  `SqliteDatabaseOpener.open_catalog`; the clock invariant ("A store has no clock") lets an adapter other than a store
  hold a clock for its own I/O, the opener's `WallClock` among its examples.
- `docs/operate.md`: persistence and the update say when a copy appears, its name, when it may be deleted, and which
  copy of an unfinished upgrade to keep (section 2); the `merge --into X X` paragraph says the destination is copied
  first. (Corrected: which copy to keep, as in section 2.)
- `docs/limits.md`: the upgrade's need in `data/` (4.5) and the copy's duration (502.5 s for 5.67 GB, 2026-10-13).
  Its migrations' duration (196 to 295 s, 2026-10-09) is checked against the 2026-10-13 spike (674.9 s for 0006 to
  0010) and corrected where touched.
- `docs/migration-4x.md`: the backup warning keeps recommending a backup and mentions the automatic copy; the first
  start gains the copy and its duration; the rollback gives the restore steps: stop the crawler, rename the copy over
  the database, remove the database's `-wal` and `-shm`, one database at a time and only one that has a `pre-0006`
  copy. *A stale `-wal` beside a restored file would be replayed onto it. A database without a copy was never
  migrated: the crawler opens the catalog first, so a failure there leaves `local.db` untouched.* (Corrected: per
  database, only one with a copy, the rename before the removal, in block 90 from the holistic review's major
  finding: removing first deleted a `local.db` that had no copy.)
- `docs/troubleshooting-start.md`: an entry for the space refusal, beside the other `MigrationError` entries; the
  restart loop, slow after an upgrade since each start digests the database and its copy, and how to halt it.
  (Corrected: the restart loop added in block 90, from the holistic review.)
- `docs/install.md`: the upgrade warning names the space needed.
- `docs/contributing/architecture.md`: the migration recipe gains `copy-before` and when a script carries it.
  (Corrected: with 4.1's extended list and the trigger bodies left out.)

## 6. Acceptance

Unit tests of the crawler's package, on real files in `tmp_path`. "A version N catalog" is one
`older_catalog.open_catalog_at(path, N)` builds, with rows in every table it seeds.

### On scripts written in `tmp_path` (blocks 30 and 40)

1. **Only a marked migration triggers a copy, wherever it sits.** No marked pending script: no file appears. The
   marked one second among the pending: one `<file>.pre-<first>.*_UTC` appears.
2. **One byte short refuses before any write.** A second connection keeps the `-wal` non-empty
   (`wal_autocheckpoint=0`). One byte below the need: `MigrationError` naming both numbers, no copy, no `.partial`,
   `user_version` unchanged. Exactly the need: a copy. `FakeFreeBytes` was asked about the database's directory.
3. **A leftover is deleted.** A complete `.partial` and a stray `.partial-journal` are gone after the open, and the
   copy passes `PRAGMA integrity_check`. Without the cleanup, the open fails (`output file already exists`).
4. **A taken name refuses.** A file at the final name: `MigrationError` naming it, its bytes unchanged, no `.partial`.
5. **A failed migration is retried on the same copy.** The first pending script is marked and fails after writing
   rows. The first open raises `MigrationError` naming it and leaves one copy. The clock moves a minute and a leftover
   `.partial` is planted; the second open raises the same error. One copy remains, same inode and `st_mtime_ns`, and
   the leftover is gone.
6. **A changed database gets a new copy.** After a failed open as in 5, rows are added at the same version; the clock
   moves; the next open leaves two copies, the first unchanged.
7. **An unreadable candidate is not reused.** Junk bytes at a more recent `pre-<NNNN>.*_UTC` name: a new copy, the junk
   file unchanged.
8. **The digest discriminates** (`test_database_digest.py`): equal on a database and its `VACUUM INTO` copy; different
   when a row changes, a row moves to another table of the same shape, the schema changes or the `user_version`
   changes; equal when the same rows are inserted in another order.
9. **The directive is parsed.** `_load_scripts` reads `copy-before`; a misspelled directive still raises.

### On the shipped scripts (block 50)

10. **A version 5 catalog leaves one copy**, `catalog.db.pre-0006.*_UTC`, named from the `FakeWallClock`, at version
    5, its rows equal to the catalog's before the open, table by table. The catalog ends at the latest version.
11. **Nothing pending, nothing copied.** A second open of the migrated catalog adds no file.
12. **A new file is not copied.** Only the database and its WAL files exist after the open.
13. **A marked migration further down is found.** A version 9 catalog (0010 unmarked, then 0011 marked) leaves one
    `catalog.db.pre-0010.*_UTC` at version 9.
14. **`local.db` follows the same rule.** A version 5 `local.db` leaves one `local.db.pre-0006.*_UTC` at version 5.
15. **The directives match the statements** (4.1's test). Removing the directive from catalog 0006, adding it to
    0013, or an `ALTER TABLE ... DROP COLUMN` in an unmarked script written for the test, fails it.
16. **The compositions pass real values.** `merge --into` on a version 5 catalog through `build_command_line(...)`, as
    `tests/composition/test_command_line.py:61-75` runs `merge`, leaves one copy; so does `merge --output --force`
    over a version 5 file; no source is copied. One run of `test_crawler_composition_wiring.py` on a seeded version 5
    catalog leaves one. In both, the copy's name parses to an instant between two real UTC readings around the call.

## 7. Blocks

| Block | Branch | Content | Estimate |
|---|---|---|---|
| 10 | `refactor/sqlite-database-opener` | the opener without a copier yet (4.6): its tests, then the class, the copier's constructor, both compositions; the old functions kept for the tests | about 140 lines, 8 files |
| 20 | `refactor/tests-open-through-the-opener` | mechanical: the tests open through the support helper, the old functions removed | about 150 lines, 33 files (exemption) |
| 30 | `feat/pre-migration-copy` | criteria 1 to 4 and 9, then 4.1's grammar, 4.2 without step 3, 4.3, 4.5, `SqlitePreMigrationCopier` and its wiring, `FakeFreeBytes` | about 430 lines, 15 files |
| 40 | `feat/reuse-a-matching-copy` | criteria 5 to 8, then 4.2's step 3 and 4.4 | about 310 lines, 5 files |
| 50 | `feat/mark-row-changing-migrations` | criteria 10 to 16 with 4.1's test, then the marks, `AGENTS.md` | about 220 lines, 17 to 19 files |
| 60 | `docs/pre-migration-copy` | section 5's docs under `docs/`; drafts the handoff | about 130 lines, 6 files |
| 80 | `fix/pre-migration-copy-review` | the holistic review's findings in code, tests and ignore files | 95 lines, 16 files (measured) |
| 90 | `docs/pre-migration-copy-wrap` | the closing block: the holistic review's findings in the documents, `BACKLOG.md`, the handoff | a few lines |

- **Every block is written test first** (`AGENTS.md`, Strict TDD): each test is watched failing before the code
  that answers it. Block 20 moves imports and adds no behaviour.
- **Block 20 asks for the mechanical exemption**, on its row: import lines moved and functions removed, nothing else.
  Block 10 holds the non-mechanical part of the move.
- **No shipped script is marked before block 50**, so blocks 30 and 40 change nothing in production when they reach
  `main`, each push of which publishes the `main` image.
- Estimates by agent `migcopy-estimate` on `main`, within about 25 %. If block 30 passes a bound, the space check moves
  to block 40; if block 50 does, criterion 16 and `AGENTS.md` move to block 60.
- Cut from `main` at `cd307232` or later.
- (Corrected: block 80 added. The holistic review's fixes touch 16 files in code and tests, and 6 more in the
  documents: together they pass the 20-file bound, so the closing block split in two, code first.)

## 8. Limits and scope

### Accepted limits

- **A stop during the copy is not seen until the open returns.** The open blocks the event loop before the signal
  handlers act, so `docker stop` kills the process after its grace period; the next open deletes the `.partial`. The
  migrations already behave this way.
- **A failure after a marked migration committed makes another copy.** If 0006 commits and 0007 fails, the database
  matches no copy and 0008 and 0011 are still pending: a `pre-0007` copy is made, once. At most one per version from
  the first pending to the last marked, six per database on the node. Each holds the live pages only, and the earliest
  stays the real backup.
- **SQLite's temporary files are not counted** in the need.
- **4.1's test cannot see a row rewritten by an existing trigger.** A plain `INSERT` that fires a trigger created by
  an earlier script, and whose body deletes or updates rows, leaves the script unmarked. (Corrected: added with 4.1's
  exclusion of trigger bodies, operator 2026-10-27.)
- **4.1's test cannot see a statement sqlfluff does not parse.** `poe sql-lint` fails on one unless its line carries
  `-- noqa: PRS`, as 0009's `VACUUM` does; such a line is visible in review.

### Adjacent backlog items

- **A copy before a migration that rewrites rows**: shipped by this lot, removed.
- **Every stamp an integer of microseconds since the epoch**: stays open, its own lot. Its catalog part waited for
  this lot; the closing block drops that wait from the entry.
- **The Grype scan back on p2pwatch at the v5 release**: stays open; the v5 waits for a second network.
- **Multi network, stage 5**: its free-space check per client output directory stays open. It reads the clients'
  download disks through `FreeSpaceMeter`, another filesystem and another promise.

### Not in this lot

- No release (section 1).
- No change to the restart policy (D9).
- No measurement of the copy or the digest on the node itself.

## Appendix A. Facts

Read by `migcopy-facts` on 2026-10-27, recounted by the spec review.

- **The node** (`/home/geoffrey/Projets/mulewatch/data/`, read from the files' headers): `catalog.db` and `local.db`
  at version 5, the catalog 7.55 GB plus a 10 MB `-wal`.
- **The callers.** The crawler's composition opens both databases (`crawler_composition.py:312-314`), with a
  `SystemWallClock` already built (`:303`). `merge` opens its destination (`sqlite_catalog_copier.py:143`), for
  `--into` and for `--output --force` over an existing file (`merge_catalogs.py:36-42`), and attaches its sources
  without migrating them (`sqlite_catalog_copier.py:170-180`). `merge` builds no clock (`command_line.py:23-43`).
- **The tests** call `open_catalog` and `open_local` on 59 lines of 31 files, and the private functions of `connection.py`
  through `older_catalog.py` and `test_connection.py`.

Which migrations change rows:

| Database | Version | Changes rows | How |
|---|---|---|---|
| catalog | 0005 | yes | `DROP TABLE file_verifications` |
| catalog | 0006 | yes | drops `source_observations` and `sources` |
| catalog | 0007 | yes | rebuilds observations into variants, drops `file_observations` |
| catalog | 0008 | yes | rebuilds four tables keyed by `file_id` |
| catalog | 0009 | no | `VACUUM`, no row changes |
| catalog | 0011 | yes | drops stage 4's source tables |
| local | 0004 | yes | drops `verification_tasks`, `UPDATE downloads` |
| local | 0005 | yes | `UPDATE downloads` fills a new column |
| local | 0006 | yes | `DELETE FROM scheduler_state` |
| local | 0007 | yes | rebuilds `downloads` |
| local | 0010 | yes | two `UPDATE`s |
| local | 0011 | yes | drops `scheduler_state` |

Every other script adds a table, a column or an index, or renames a column: 11 of 25 scripts change rows, 8 of them
pending on the node.

## Appendix B. Measurements

By `migcopy-measure`, 2026-10-27, SQLite 3.49.1, on tmpfs (CPU only, a lower bound). The spec review re-ran the facts
in the core image `main` (SQLite 3.46.1): they match.

- `VACUUM INTO` keeps the `user_version`, the rowids (gaps included) and the committed rows still in the `-wal`. The
  copy is in `journal_mode` delete. It refuses to run inside a transaction.
- A non-empty target fails with `output file already exists`, a valid copy or a half one alike; an empty one works; a
  partial file without its journal fails with `file is not a database`.
- A copy killed midway leaves a file whose page 1 is zeros, and a hot `-journal`.
- A rolled-back transaction that spilled 407 MB to the `-wal` leaves the counts, the digest, the database file's mtime
  and its header unchanged, and changes the `-wal`'s and `-shm`'s mtimes.

| Operation on 1.31 GB | Time | Linear at 7.5 GB |
|---|---|---|
| `VACUUM INTO` | 2.2 s | about 12 s |
| `count(*)` of every table | under 0.05 s | |
| the digest, Python, one side | 10.4 s | about 60 s |

sqlfluff 4.3.0's parse of every shipped script (probe by the lead, 2026-10-27) finds the row-changing statements of
appendix A's table exactly, and none in the other scripts; catalog 0009 is unparsable (`VACUUM`).

On a real disk, reading and writing dominate: section 4 of the 2026-10-13 spec measured the copy of the node's catalog
at 502.5 s for 5.67 GB, on Docker Desktop.

# v5 lot 2: the migration and the first start

Tier Spec. Discussed with the operator on 2026-11-06 and 2026-11-07, as lot 2 of
`agents/specs/2026-11-04-v5-release-readiness.md` (the umbrella), whose decisions D4 to D9 this lot implements. Its
findings are the umbrella's appendix A "Lot 2". The decisions are the operator's; their reasons are those given in the
discussion, the lead's included where the operator accepted a recommendation. Every measurement was re-run on
2026-11-06 on a reflink copy of the operator's node and on a synthetic catalog (appendix C). The spec's commit marks
the umbrella's D4 (`(Corrected: an out-of-space during the block refuses after the copy, lot 2's D1)`), D6
(`(Corrected: the copy's share written in place of an expected wait, lot 2's D3)`) and D7
(`(Corrected: refined by lot 2's D4)`).

## 1. In short

Upgrading a 4.x node migrates its catalog for about ten minutes. Today a stop during those minutes makes the next
start write a second full copy of the catalog, enough to refuse a node whose disk is sized as the docs say, and the
log stays silent for six minutes, then four, which is exactly when an operator restarts. The lot makes every
migration of one start a single all-or-nothing step, so a stop costs only the time spent; makes the start report its
progress; gives back the memory the migration used and bounds what it can take; and has `merge` refuse to write into
a catalog a running crawler holds. On the way it closes the small defects the audit found in the same code.

## 2. What the operator will see

- **A stop or a reboot during the upgrade costs only the time spent**: the next start finds its copy, checks it still
  matches and reuses it, with no second copy and no extra disk.
- **The first start's log shows a line at least every 30 seconds**: what it is doing, how far the copy is, and that a
  stop now only costs the time spent.
- **Short of disk space, the start refuses in one line**, in gigabytes, saying how much to free: before the copy
  when the usual reserve is missing, during the migrations in the rare case it is not enough: the database is then
  left at its starting version, or, when the space ran out after the migrations committed, migrated with only its
  reclaim to redo.
- **A migration refused on a value names the value**, not "user-defined function raised exception".
- **The crawler gives back the migration's memory**: about 100 MB after an upgrade instead of about 400 MB, and a
  catalog of many distinct observations no longer pushes the migration past the container's 2 GB.
- **A merge refuses to write into a catalog a running crawler holds** and says to stop the node; `merge --output`
  still reads a running node's catalog.
- The operator pages (`limits.md`, `operate.md`, `troubleshooting-start.md`, the migration guide) are lot 7's
  (umbrella D19): this lot lists what they must say (section 6).

## 3. Decisions

- **D1. All the migrations a start applies run together in a single transaction, and the database's schema version
  is written once, at its end; the free-space reserve stays the copy plus the file's size, and a lack of space during
  the block rolls it back and refuses in the same one line.** *Today each migration commits alone, so a stop after the first leaves an intermediate version
  whose next start writes a second full copy (7.5 GB on the operator's node) that no release can read; one
  transaction leaves the database at its starting version, whose copy the next start reuses (umbrella D4). The
  reserve covers the operator's catalog with room to spare (8.1 GB used, 15.3 GB reserved), while covering a catalog
  that folds nothing would take 3.2 times the catalog, 31 GB on the operator's node; with one transaction a refusal
  during the block leaves the database at its starting version, so the umbrella's "never in the middle of the block"
  loses its reason.* The operator chose it on 2026-11-07. Block 10.
- **D2. The final space reclaim leaves the numbered migrations: the opening compacts a database after any block of
  migrations, and at any opening where a quarter of the file or more is free pages, without a copy.** *SQLite refuses
  `VACUUM` inside a transaction, so D1 cannot hold it (umbrella D5). An upgrade frees at least its old tables (96 % of
  the operator's file, 49 % of a catalog that folds nothing), so an interrupted reclaim is replayed by the quarter
  rule, which an ordinary catalog, which only grows, never meets.* Block 10.
- **D3. The start reports each long step before it begins and every 30 seconds while it runs**: the copy (its size
  and its share written), the comparison with an existing copy, the migrations, the reclaim; it says that a stop
  now only costs the time spent; the next start says when it found an interrupted copy; a free-space refusal is one
  line in gigabytes. *Ten silent minutes are when an operator restarts, and a traceback in bytes helps nobody
  (umbrella D6). The share written stands in for the umbrella's "expected wait": the same copy took 143 s on the host
  and 380 s under Docker Desktop, and the guide gives the measured durations (lot 7).* The lines come from a thread
  beside the step: SQLite's own progress callback went up to 83 s without a call during the migrations. Blocks 20 to
  40.
- **D4. A merge refuses a destination another process holds; its sources are only read, so `merge --output` keeps
  reading a running node's catalog.** *Writing into a live catalog holds its write lock for the merge's length, and
  the crawler loses its writes (3 failed during a 16 s merge); reading it as a source cost a writer nothing (none of
  its writes failed across an 18 s `--output` merge), and it is how an operator shares a consolidated catalog.* This
  refines the umbrella's D7 ("`merge` runs on a stopped node only"), whose reason concerns writing alone; the operator
  chose it on 2026-11-06. SQLite detects the holder itself: no lock file of our own. Block 60.
- **D5. After applying migrations, the opening reopens its connection and hands the freed memory back to the system;
  the migrations' memoized functions get a bound.** *The migration leaves about 280 MB that the C library keeps but
  nothing uses, until the next restart (umbrella D8). The memo holds every distinct variant: 14 237 on the operator's
  catalog, but a catalog of a million distinct observations took the migration to 2.1 GB, past the container's
  2 GB.* Block 50.
- **D6. Two rare raw metadata shapes lose a value at the migration, accepted (umbrella D9).** *Neither exists in the
  operator's catalog, and no release since v3.0 writes them.* No block: lot 7's guide states it.
- **D7. The audit's small defects in the same code are fixed here**: a refused value named in the error, a copy that
  works on a disk refusing hard links, a dead statement in a migration. *They sit in the code this lot rewrites,
  each fix is small, and a latent defect is a defect.* Block 70.

## 4. Acceptance

Commands in appendix B.

### In tests and CI

| Check | After the lot | On main |
|---|---|---|
| A migration failing after others succeeded | the database stays at its starting version | the earlier ones stay committed |
| A restart after that failure | reuses the copy, writes no second one | writes a `pre-<next>` copy |
| A disk full during the block | rolled back, the one-line space refusal | the failing migration's error, earlier ones committed |
| A block of migrations leaving under half of the file free | compacted | compacted only by `catalog/0009` |
| A database a quarter free or more, opened with nothing pending | compacted | untouched |
| A long step of the opening | a line before it and every 30 s | a line before it, none during it |
| An interrupted copy found at the start | named in the log | deleted silently |
| Too little free space before the copy | one line, in GB, exit 1, no traceback | a 52-line traceback ending in bytes |
| The same for a merge's destination | one `Merge failed` line, in GB | one line in bytes |
| A value a migration's function refuses | the error names the function and the value | `user-defined function raised exception` |
| An opening that applied migrations | the returned connection's memo empty, the memory releaser called once | neither |
| The memoized functions over more distinct values than their bound | the cache stays at its bound | grows without end |
| A merge into a catalog another connection holds, `--into` or `--output --force` | refused, the destination unchanged | runs, the holder's writes fail |
| `merge --output` reading a held catalog | runs | runs |
| The copy's publication where hard links are refused | published, never replacing a file | fails, every start |

### On a copy of the operator's node and a synthetic catalog, at the lot's Wrap

Run by the lead on the stack's top, before the holistic review, with the audit's instruments.

| Check | After the lot | On main |
|---|---|---|
| Content after the migration | `compare.py` all OK | all OK |
| A stop during the migrations, then a restart | the copy reused, no second `pre-*` | a second full copy |
| A stop during the reclaim, then a restart | compacted at the restart | replayed (version 8) |
| A `data/` short of space | one line naming what to free | a traceback |
| The first start's log | no gap over 60 s before `crawler started` | 6 then 4 silent minutes |
| `merge --into` the catalog while a process writes it | refused before writing | the writer's writes fail |
| A synthetic catalog that folds nothing, on a disk with the reserve only | refused in one line, the database at version 5 | refused mid-way, at an intermediate version |
| The same catalog, its migration's resident memory | under 1 GB | 2.1 GB |

### On the operator's node, at rc (umbrella)

| Check | At v5.0.0 | Today |
|---|---|---|
| The crawler's resident memory after the first start | under 150 MB | 330 MB just after opening |

### What must not change

- Every observation, decision and download of a 4.x catalog survives the upgrade field by field: the Wrap's
  `compare.py`.
- The rollback copy: after a failed block, `pre-<first pending>` reads the starting `user_version` and the starting
  content (the existing copier tests, and the Wrap's stop row).
- A database newer than the code is refused; a new database gets no copy (the existing opener tests).
- `merge`'s other refusals and its idempotence (the existing merge tests).

## 5. Blocks

| # | Branch | Change | Decisions |
|---|---|---|---|
| 10 | `feat/migrations-all-or-nothing` | one transaction per start, the reclaim after it | D1, D2 |
| 20 | `feat/copy-progress-lines` | the copy's steps reported | D3 |
| 30 | `feat/migration-progress-lines` | the migrations' and the reclaim's steps reported | D3 |
| 40 | `feat/free-space-refusal-line` | the free-space refusal in one line | D1, D3 |
| 50 | `fix/migration-memory-release` | the connection reopened, the memory released, the memo bounded | D5 |
| 60 | `feat/merge-refuses-held-catalog` | a merge refuses a held destination | D4 |
| 70 | `fix/migration-small-findings` | the refused value named, the copy without hard links, the dead statement | D7 |
| 80 | `docs/v5-migration-first-start-wrap` | closing block | |

Sizes: appendix A, estimated by a Sonnet agent on this cut (`.reviews/v5-lot2-estimate.md`, about 25 % either way).

## 6. Limits and scope

### Accepted limits

- **A catalog that folds little can run out of space during the migrations** (D1): the block rolls back, the start
  refuses in one line, and every restart redoes the comparison and the block until the operator frees space. Should
  the space run out in the checkpoint right after the commit, the migrations stay committed in the WAL, consistent,
  and the reclaim refuses in the same line until space is freed.
- **A stop during the opening is acted on once the opening ends**: the crawler's signal handler runs on its event
  loop, which the opening holds (a SIGTERM 10 s into a copy alone was acted on 205 s later). Docker kills the process
  after its 10 s grace; D1 makes that harmless, the copy's partial file is deleted at the next start, and D3's lines
  say a stop costs only the time spent.
- **Reusing a copy costs a full comparison of both databases**: about 95 s per side on the operator's catalog, so
  3 minutes, against a 2 to 6 minute copy that also takes 7.5 GB.
- **A running merge makes a starting crawler fail to open the catalog** until it ends, and Docker restarts it: the
  docs say to stop the node before `merge --into`.
- **Two rare raw metadata shapes lose a value at the migration** (D6): a metadata name repeated within one reading
  keeps only its last value, and a plain `media` name beside `media.*` names is dropped. Only data written before v3
  can hold the first, no release since v3.0 writes the second, and the operator's catalog holds neither.

### For lot 7 (umbrella D19)

- `limits.md`: the first start's figures re-measured (appendix C), the free-space rule and its rare refusal during
  the migrations, a restart costs only time.
- `operate.md`: one copy per database whatever happens; `merge --into` with the node stopped
  (`docker compose stop p2pwatch`, then `docker compose run --rm p2pwatch python -m p2pwatch merge ...`);
  `--output` beside a running node.
- `troubleshooting-start.md`: the new refusal lines (space, a held catalog, a refused value).
- The migration guide: the two metadata shapes D6 accepts losing; the first start's duration.

### Adjacent backlog items

- **`merge` refuses a source whose schema is not the node's**: D4 refuses a held destination, not a schema; it stays
  open.
- The others are another lot's or after v5 (umbrella, "Adjacent backlog items").

## Appendix A. Design, block by block

Every block is written in strict TDD (workflow, Act): each new behaviour's test is written first and watched failing,
its failure line in the block report. Every block is green alone: `dead-code-check` refuses a port or method whose
caller lands in a later block.

### Block 10: one transaction per start, the reclaim after it (D1, D2)

- `_apply_migrations` runs `BEGIN`, every pending script in order, `PRAGMA user_version = <latest>`, `COMMIT`; any
  `sqlite3.Error` rolls the whole block back and raises `MigrationError` naming the migration that failed. The check
  that a script left the transaction open stays, per script. `secure_delete` and `cache_size` are read before the
  block and restored after it (0007 and 0008 set them), `temp_store` as today.
- A `SQLITE_FULL` during the block (`sqlite3.Error.sqlite_errorcode`) raises a distinct `MigrationError` subclass,
  which block 40 turns into the one-line refusal; until then it reads as today's failure, naming the migration.
- The migration outside a transaction is deleted, as the operator asked on 2026-11-07: dead once 0009 leaves, and
  broken with D1, since a script outside the transaction would break the all-or-nothing. Gone: `_NO_TRANSACTION` and
  its branch in `migration_scripts.py`, `Migration.transactional`, the opener's `_run_outside_transaction` and its
  choice in `_run_restoring_pragmas`, their tests, and every mention in the contributor docs. A script still opening
  with `-- migration: no-transaction` falls under the existing refusal of an unknown directive, with no code of its
  own.
- `catalog/0009_vacuum.sql` keeps its number and holds only a comment saying the opening reclaims since lot 2: a
  development database past version 9 is unaffected, and no release ever shipped it (v4.1.0 stops at 5).
- The reclaim, in `open` (not `open_reader`), after the migrations: when a block was applied, or when
  `freelist_count * 4 >= page_count`: `VACUUM` then `PRAGMA wal_checkpoint(TRUNCATE)`, outside any transaction, a
  `SQLITE_FULL` raising the same subclass. Measured: 4.8 s on the operator's catalog (1 818 073 free of 1 895 041
  pages), the WAL peaking at 278 MB, the file 277 MB; the catalog that folds nothing ends its block 49 % free.
- The copier is unchanged: its prefix is still the first pending version, so after a failed block the next start
  finds `pre-<first>` and compares it (`_matches_its_latest_copy`). The free-space check is unchanged (the copy's live
  pages, the file's size again, the WAL).
- `docs/contributing/architecture.md`: 8.1, one transaction per start, not per script, no `no-transaction` script,
  the reclaim; line 500, "`catalog/0009` rend au disque, par un `VACUUM`", now the opening's reclaim.
- Tests: the opener's with scripts in a temporary directory (a second script failing leaves the version and the
  first's tables absent; a `no-transaction` directive refused; the reclaim after a block leaving under half free, and
  on an opening with nothing pending at a quarter free, not below; a full disk during the block, through a database
  whose `max_page_count` is set low, rolls back and raises the subclass); the existing interrupted-copy tests
  adjusted.
- About 290 to 480 lines, 9 to 11 files: near the bound, the first to split along the reclaim if it passes.

### Block 20: the copy's steps reported (D3)

- A driven port `Ticker`, which calls a callback every period from beside a long synchronous operation until it
  ends, and its adapter `ThreadingTicker`: a thread waiting on a `threading.Event` between calls, which runs while
  the opening holds the asyncio loop since SQLite releases the GIL. It is a clock adapter, beside `WallClock` and
  `MonotonicClock`: `MonotonicClock.sleep` is asynchronous on the very loop the opening holds, and a synchronous sleep
  added to it would let any core code block that loop. Its contract, its fake (calling back on demand), `tach.toml`;
  the crawler's and the command line's compositions pass the adapter to the copier, and in block 30 to the opener.
- `.claude/rules/glossary.md` gains `ticker`; `.claude/CLAUDE.md`'s hard rule reads "everything else injects
  `WallClock`, `MonotonicClock` or `Ticker`", and `.claude/rules/stores.md` follows if it names the clocks.
- Lines, as the operator reads them (wording the teammate's):
  - before the copy: the database, the size the copy will write in GB, and that a stop now only costs the time spent;
    every 30 s, the GB written and the share (the `.partial` file's size against the live pages');
  - before the comparison with an existing copy: the copy compared and why; every 30 s, the elapsed time;
  - when `_delete_leftovers` deletes a partial copy: the previous start's copy was interrupted and starts over.
- Tests: the copier with the fake ticker (each line, in order, the share computed); the adapter through its contract
  (a callback per period, none after the end).
- About 330 to 400 lines, 14 to 17 files (`.reviews/v5-lot2-estimate.md`).

### Block 30: the migrations' and the reclaim's steps reported (D3)

- The opener reports, through block 20's port: before the migrations, from which version to which, in one step, and
  that a stop rolls them back; every 30 s, the migration running and the elapsed time; before the reclaim, the free
  space it gives back.
- Tests: the opener with the fake ticker.
- About 80 to 110 lines, 4 or 5 files.

### Block 40: the free-space refusal in one line (D1, D3)

- A domain error beside `StoreError` (the command line, a driving adapter, cannot import the SQLite adapter's
  `MigrationError`), raised by the copier's free-space check and by block 10's `SQLITE_FULL` path: the directory, the
  GB needed when known, the GB free, the GB to free.
- `ArgparseCommandLine` prints it as one line, exit 1, as it does `InvalidConfigError`. For a merge, the catalog
  copier maps it to `CatalogCopyError`, as it maps `PersistenceError` today, so `merge` keeps its one `Merge failed`
  line, now in GB. Every other `MigrationError` keeps today's path.
- Tests: the copier's refusal; the crawl's line; the merge's line.
- About 100 to 160 lines, 6 to 8 files.

### Block 50: the connection reopened, the memory released, the memo bounded (D5)

- The opening's order: the migrations, the reclaim, then, when migrations were applied, the connection closed and
  opened again (same pragmas, block 60's locking mode included, `remove_migration_sql_functions` again), then an
  injected memory releaser called once.
- The releaser's adapter calls glibc's `malloc_trim(0)` through `ctypes`, and does nothing where the C library has
  none; the composition passes it to the crawler's and the command line's openers.
- `create_memoized_function` takes a bound (`functools.lru_cache(maxsize=...)` in place of `cache`), sized to hold
  the operator's 14 237 variants with room (65 536 suggested); the reopen still drops it.
- Observables: the returned connection's memo holds no entry (the memo's `cache_info` reachable through what
  `create_memoized_function` registers, the teammate's choice of seam); the releaser's call count on a fake; the
  adapter resolves `malloc_trim` on the gate's glibc; the memo stays at its bound over more distinct values.
- About 210 to 330 lines, 12 to 14 files.

### Block 60: a merge refuses a held destination (D4)

- The merge's destination is opened in SQLite's exclusive locking mode (`PRAGMA locking_mode=EXCLUSIVE` before its
  first access, no busy wait), so the opening fails while another connection holds the file, even idle, `--into` or
  `--output --force` alike; the refusal reaches the command line as a `MergeError`: the destination is held by
  another process, stop the node first. The lock lasts the merge, block 50's reopen included, so a crawler cannot
  open the catalog meanwhile.
- The sources keep their read-only attach.
- Probed (appendix C): an idle WAL connection, or an idle `mode=ro` reader, makes the exclusive opening fail with
  `database is locked`; without one it succeeds, and a normal connection reopens the file in WAL afterwards; a WAL
  left by a killed writer opens whole.
- `.claude/rules/merge.md`: the refusal.
- Tests: `--into` with an idle connection open on the destination (refused, destination unchanged), without (merged);
  `--into` a destination that needs a migration, held after it (the reopen keeps the lock); `--output` with a
  connection open on a source (merged).
- About 140 to 230 lines, 6 to 8 files.

### Block 70: the refused value named, the copy without hard links, the dead statement (D7)

- Each migration SQL function registered by `register_sql_functions` keeps the exception it raised and the value it
  was given, and `MigrationError` names them: `migration 7 failed: iso_to_micros('2026-07-04 12:00') raised
  ValueError: ...`, the value cut to 100 characters. SQLite forwards only its fixed text.
- `_rename_without_replacing` takes the linking function as a parameter (`os.link` by default); when it is refused
  (`EPERM`, `ENOTSUP`, `EOPNOTSUPP`), the copy is published by `os.rename` once the final name is checked absent. Only
  one opener writes a database's copies, and the final name carries the second. No placeholder file: a crash between a
  reservation and the replace would leave an empty file that looks like a rollback copy.
- `local/0010_backoff_states.sql`: the `UPDATE ... 'channel_backoff'` that can never match is deleted (`local/0006`
  deleted those rows; never released).
- Tests: a migration over an instant without a time zone names it; the publication with an injected link raising `EPERM` (on main the
  copy fails), and an existing final name refused on both paths.
- About 190 to 320 lines, 8 to 10 files.

### Block 80: closing block

- The holistic review's fixes, `BACKLOG.md` reconciled, the handoff; the umbrella's lot 2 rows marked done or
  corrected.

## Appendix B. Acceptance, in detail

| Row | Command, and the output that fails it |
|---|---|
| Content | `compare.py <pristine> <migrated> catalog` (audit instruments, `migration-e2e/`); fails on any `DIFF` |
| Stop during the migrations | `kill_test.py` (audit, `schema-migrations/`) at full scale, SIGKILL 60 s into the block, restart, `ls data/`; fails on a second `pre-*` |
| Stop during the reclaim | SIGKILL during the reclaim, restart, file size; fails above 300 MB |
| Short of space | `freespace.sh` (audit, `migration-e2e/`); fails on a traceback or a figure in bytes |
| First start's log | the crawler's log with timestamps on the copy, through `crawler started`; fails on a gap over 60 s |
| Merge into a written catalog | `writer.py` (lead's probe) on the migrated copy, then `merge --into` it; fails if the merge runs or a write fails |
| Folding nothing | `make_nofold.py` (lead's probe) at 1 000 000 observations on a filesystem sized to the reserve (a loop or tmpfs mount); fails on a traceback, or on a `user_version` other than 5 after the refusal |
| Its memory | the probe's resident memory sampled through the block; fails at 1 GB or more |
| Memory, at rc | `docker compose exec p2pwatch grep VmRSS /proc/1/status` once the first start's reevaluation ends; fails at 150 MB or more |

The lead's probes are committed beside the audit's, under `agents/reference/2026-11-04-v5-audit-instruments/lot2/`,
in the first block.

## Appendix C. Facts

Measured 2026-11-06 on a reflink copy of the operator's node (`catalog.db` 7 762 018 304 bytes at version 5, its WAL
10 MB), and on a synthetic 4.x catalog of 1 000 000 observations sharing no variant (402 083 840 bytes), on the host
(Python 3.13.6, SQLite 3.49.1; the image ships 3.46.1). Outputs in the lead's scratchpad (`one_tx.jsonl`,
`mem.jsonl`, `compare_one_tx.txt`, `console_outputs.txt`).

| Measure | Result |
|---|---|
| Copy (`VACUUM INTO`) | 143 s on the host (380 s under Docker Desktop in the audit), 7 495 532 544 bytes |
| Migrations 6 to 15, one transaction | 183 s and 195 s (two runs): 0007 166 to 178 s, 0008 14 s, the others under 0.1 s, commit and checkpoint 3 s |
| Peak during the block | WAL 640 MB, the file unchanged; beyond the original: copy + WAL, 8.1 GB, against 15.3 GB reserved |
| After the block | 1 818 073 free of 1 895 041 pages |
| Reclaim | 4.8 s, WAL peak 278 MB, file 277 MB, `quick_check` ok |
| Content | `compare.py` against the original: `SUMMARY all OK` (15 763 676 observations in bijection, 16 477 decisions) |
| Comparison with a copy | `database_digest` 98 s on the live database, 89 s on its copy, equal digests |
| SQLite's progress callback (every 10⁶ instructions) | longest gap 2.3 s during the copy, 58 s and 83 s during the block (two runs) |
| SIGTERM 10 s into a copy alone, under `PosixProcess` | the copy runs to its end (215 s), then the process exits 0 |
| Resident memory after the block, then after `malloc_trim(0)` | 317 MB, then 52 MB (no reopen) |
| Synthetic, folding nothing: the block | 48.6 s; 78 913 free of 160 840 pages after it (49 %) |
| Synthetic: peak beyond the original | 1.30 GB (file grown to 659 MB beside a 663 MB WAL at the commit's checkpoint, copy 379 MB) against 0.80 GB reserved: 3.2 times the catalog |
| Synthetic: resident memory | 2 134 MB after the block, 1 870 MB after `malloc_trim(0)`, 27 MB once the connection closed: the memo |
| `merge --output` from a catalog a writer uses (Python's 5 s busy timeout, a write every 0.2 s over 60 s) | merge 18 s; 299 writes over the run, about 90 within the merge, none failed |
| `merge --into` the same catalog | 16 s, 3 writes failed `database is locked`, the slowest 5.01 s |
| `PRAGMA locking_mode=EXCLUSIVE` beside an idle WAL connection | its first access fails `database is locked`; alone it succeeds, and a normal connection reopens the file in WAL (the reviewer also: beside an idle `mode=ro` reader, and a WAL left by a killed writer) |
| A page in one transaction | written once to the WAL however often it changes (the reviewer's `walonce.py`) |

# Handoff: v5 lot 2, the migration and the first start (tier Spec)

Drafted by block 70's teammate from the block reports, corrected by the closing blocks (75 and 80). Spec:
`agents/specs/2026-11-06-v5-migration-and-first-start.md`, lot 2 of `agents/specs/2026-11-04-v5-release-readiness.md`
(the umbrella), whose D4 to D9 it implements.

## Current state

- **A start's migrations are one transaction** (D1): `_apply_migrations` runs `BEGIN`, every pending script, writes
  `PRAGMA user_version` once, then `COMMIT`; any failure or kill leaves the database at its starting version, and the
  next start finds `pre-<first pending>`, compares it and reuses it. A script that closes the transaction is still
  refused, naming its migration. The `-- migration: no-transaction` directive is gone and refused as an unknown one;
  `catalog/0009_vacuum.sql` holds only a comment.
- **The opening reclaims at a quarter free** (D2, the operator's decision of 2026-11-07): at any opening, after a
  block as without one, where a quarter of the file or more is free pages, `VACUUM` then `wal_checkpoint(TRUNCATE)`,
  outside any transaction, under `temp_store=FILE`. A 4.x upgrade frees 95 % of the operator's file, so it is
  compacted, and a stop during the reclaim makes the next start compact it; a block that frees nothing (a column
  added) rewrites nothing.
- **The opening's order** (D5): the copy, the block, then, when migrations were applied, the connection closed and
  opened again through `_connect` (the memo, the page cache and the scripts' pragmas dropped), the reclaim on the new
  connection, `iso_to_micros` removed, then `MemoryReleaser.release()` once. `GlibcMemoryReleaser` calls
  `malloc_trim(0)` through `ctypes`, a no-op without it. The memoized SQL functions keep at most 65 536 entries.
- **The start reports its long steps** (D3) through the driven port `Ticker`, a clock adapter
  (`ThreadingTicker`, a thread of its own, since the opening holds the event loop): the copy (its size, then every
  30 s the GB written and the share), the comparison with an earlier copy (every 30 s the elapsed time), an
  interrupted copy found and deleted, the block (from which version to which, then every 30 s the migration running
  and the time since the block began), the reclaim (the GB and the share of the file it gives back, then every 30 s
  the elapsed time). Each says a stop now costs only the time spent.
- **Short of space, one line in GB** (D1, D3): the domain's `OutOfSpaceError`, raised by the copier's check before
  the copy (the need rounded up, the free space rounded down, the space to free their difference, so the three
  figures agree) and by the opener on `SQLITE_FULL` during the block or the reclaim (the free space only, measured
  once the WAL is emptied), with the database's state, the reclaim's version read from the database. The crawl
  prints it as one line, exit 1; `merge` as its one `Merge failed` line, exit 2. The image sets
  `SQLITE_TMPDIR=/data`, so SQLite's temporary files land on the disk the check measures.
- **A held database is refused** (D4): `HeldDatabaseError`, in the domain since block 75, raised when `SQLITE_BUSY`
  meets a connection's first access, `<path> is held by another process`. A merge opens its destination with
  `PRAGMA main.locking_mode=EXCLUSIVE` and no busy wait, the reopen after a block included, and prints
  `Merge failed: destination <path> is held by another process: stop the node first`; sources keep their read-only
  attach, so `merge --output` reads a running node's catalog. A crawler started during a merge refuses after its 5 s
  busy wait in one line, `Database in use, refusing to start: <path> is held by another process`, exit 1.
- **The audit's small defects** (D7): a migration failing in a SQL function names the call
  (`migration 7 failed: iso_to_micros('2026-07-04 12:00') raised ValueError: ...`, the arguments cut to 100
  characters); a filesystem refusing hard links (`EPERM`, `ENOTSUP`) gets its copy published by `os.rename` once the
  final name is checked absent; `local/0010` no longer renames the `channel_backoff` key.

## What was built, block by block

| # | PR | Block | Lines, files |
|---|---|---|---|
| 10 | #649 | one transaction per start, the reclaim after it | 339, 10 |
| 20 | #650 | the copy's progress lines, the `Ticker` port | 439, 16 |
| 25 | #652 | the comparison's progress lines | 81, 2 |
| 30 | #653 | the migrations' and the reclaim's lines | 153, 9 |
| 40 | #654 | the free-space refusal in one line | 328, 19 |
| 45 | #655 | `SQLITE_TMPDIR=/data` in the image | 6, 3 |
| 50 | #656 | the connection reopened, the memory released, the memo bounded | 354, 19 |
| 60 | #657 | a merge refuses a held destination | 248, 8 |
| 70 | #658 | the refused value named, the copy without hard links, the dead statement | 234, 10 |
| 75 | the one after #658 | the free-space figures agreeing, the crawl's held catalog in one line | 111, 13 |
| 80 | the closing one | the reclaim at a quarter free alone and ticked, the review's other fixes, the records | 129, 8 |

- **Three splits, each for a bound**: block 20 into 20 and 25 (519 lines with the comparison's lines, which moved to
  25); block 40 into 40 and 45 (the file bound; 45 holds the image's `SQLITE_TMPDIR=/data`, the operator's option (b)
  on block 40's class 2 question); the closing block into 75 and 80 (20 files, the bound being under 20: 75 holds the
  review's code fixes that touch no reclaim, 80 the reclaim and the records).
- **Two fix-backs**: block 10, the word "stamp" for writing the schema version, which the operator rejects (it reads
  "written"); block 20, size-driven compromises undone, which took it past the bound and caused its split.
- Departures, each marked `(Corrected: ...)` in the spec (27 marks), two in the umbrella (D5 and the space row):
  - Block 10: `temp_store=FILE` spans the reclaim as well as the block; the `no-transaction` refusal is tested in
    `test_migration_scripts.py`; `test_migration_0009.py` deleted with its `tests_without_unit` entry; a failure at
    the commit names `the commit at version <N>`, at `BEGIN` `the block's start`. Its `SQLITE_FULL` subclass of
    `MigrationError` was replaced in block 40 by the domain's `OutOfSpaceError`.
  - Block 20: `ThreadingTicker` takes a `MonotonicClock` for the elapsed time it passes; `TickerContract` has an
    abstract hook `let_periods_pass`; only the `.partial` gets the "interrupted" line, its `-journal` deleted silently.
  - Block 30: the reclaim's line gives the share of the file beside the GB and says a stop costs only the time spent.
    The GB formatting moved to a module of its own, then to the domain in block 40.
  - Block 40: after a `SQLITE_FULL` the line gives no "to free", the need being unknown (the lead confirmed that
    reading of "the GB needed when known"); the opener takes the free-bytes meter.
  - Block 45: the reserve (the copy plus the file's size again) must now also hold SQLite's temporary files, which
    appendix C's 8.1 GB peak did not count; the Wrap measured at most 8.7 GB against 15.3 GB reserved.
  - Block 50: the reopen comes before the reclaim, not after it: the `VACUUM` gets the build's pragmas with no
    restore code, and block 10's restore of `secure_delete` and `cache_size` is deleted. `MemoryReleaser` has a
    contract; the memo's seam is `create_memoized_function`'s return value, and the opener's test proves the
    connection is a new one.
  - Block 60: `SQLITE_BUSY` at a first access raises `HeldDatabaseError` in every mode; `_BUSY_TIMEOUT_SECONDS = 5.0`
    spelled out; a reopen held in the instant after the close refuses (the database then migrated, its copy kept, its
    reclaim replayed by the next opening), since SQLite cannot hand an exclusive lock between connections. Its tests
    sit in `test_sqlite_database_opener_exclusive.py`.
  - Block 70: the failed call is kept by a `SqlFunctionFailures` the opening creates and hands to
    `register_sql_functions`; the whole argument list is cut to 100 characters, then `...`. The spec said `local/0010`'s
    `UPDATE` "can never match": code of 2026-10-10 to 2026-10-13, never released, wrote `channel_backoff` again after
    `local/0006`, so a development `local.db` at 6 to 9 could hold it; `local/0011` drops `scheduler_state` whole, so
    the outcome is the same either way.
  - Block 75: `HeldDatabaseError` moved from the SQLite adapter's errors to the domain (a `StoreError`), since the
    command line, a driving adapter, cannot import the SQLite adapter; `gigabytes_rounded_up` gave way to
    `gigabyte_tenths_rounded_up`, `gigabyte_tenths_rounded_down` and `gigabytes_from_tenths`.
  - Block 80: the reclaim's out-of-space version is read from the database (`PRAGMA user_version`) in place of a
    ternary over the pending migrations.

## The holistic review's findings and their exits

`.reviews/v5-lot2-holistic.md`: 9 MINOR, no CRITICAL, no MAJOR; plus the lead's own.

| # | Finding | Exit |
|---|---|---|
| 1 | "after any block" rewrites the whole catalog at every future upgrade, unchecked for space, the reclaim unticked | fixed, block 80: the quarter rule alone (the operator's decision of 2026-11-07), the reclaim ticked every 30 s |
| 2 | appendix B's instruments no longer run; the Wrap's probes only in the lead's scratchpad | fixed, block 80: `wrap_open.py`, `wrap_kill.py`, `wrap_space.py` committed under `lot2/`, appendix B points at them, the six stale instruments say in their first line they were written for main before the lot (`fe691fbc`) |
| 3 | the spec's departures not marked | fixed, block 80: 27 `(Corrected: ...)` marks |
| 4 | nothing proves `release()` calls `malloc_trim` | fixed, block 80: a recording C library asserts one call with a pad of 0 |
| 5 | the reclaim's out-of-space line asserted by no test | fixed in part, block 80: the version read from the database, no ternary left; the line itself is an accepted limit, written in `docs/contributing/testing.md` section 6 (only a sized tmpfs makes a `VACUUM` fail on space) |
| 6 | `migration 8 running, 210 s elapsed` reads as 210 s of migration 8; the copy's share runs ahead of its time | fixed, block 80: `210 s since the block began`; the copy's figures handed to lot 7 below |
| 7 | the crawl's held catalog a traceback, two wordings | fixed, block 75: one line, exit 1, "another process" in both |
| 8 | tests that never failed first | fixed, block 80: each shown failing by a mutation (below); `printenv SQLITE_TMPDIR` runs in CI only, never watched failing locally |
| 9 | 0007's and 0008's comments name a restore that is gone | fixed, block 80 |
| lead | the refusal could read `0.8 GB needed, 0.2 GB free, 0.7 GB to free` | fixed, block 75: the need rounded up, the free space down, the space to free their difference |

The eighth finding's mutations (block 80):

| Test | Mutation | Failure |
|---|---|---|
| `TestFakeTicker`'s contract | `FakeTicker.tick()` calls back nothing | two tests, `E       assert False` |
| `test_an_opening_that_migrated_leaves_no_connection_open` | the reopen leaves the first connection open | `E       assert [<warnings.Wa...>] == []` |
| `test_a_database_held_alone_opens_in_wal_once_closed` | the same | `HeldDatabaseError: ... is held by another process` at the exclusive opening: the test guards SQLite's behaviour, which no mutation of the code reaches without breaking the opening |
| `test_open_removes_iso_to_micros_once_migrated[reopened after a block]` | `remove_migration_sql_functions` called before the reopen (the review's leaking reopen leaves it green) | `Failed: DID NOT RAISE OperationalError` |

## The Wrap's measurements

By the lead on 2026-11-07, on the stack's top before blocks 75 and 80 (`899b617a`), with `lot2/wrap_open.py`,
`wrap_kill.py` and `wrap_space.py`; outputs in the lead's scratchpad (`wrap_open.log`, `wrap_compare.txt`,
`wrap_kill1.log`, `wrap_kill2.log`, `wrap_temp.log`). Block 80's rule compacts the same: the upgrade leaves 95 % free.

| Row | Result |
|---|---|
| Content | on a reflink copy of the operator's catalog, `compare.py` `SUMMARY all OK` |
| The first start | 5 min 56 s on the host: the copy 1 min 56 s, the block 3 min 55 s, the reclaim 5 s; no log gap over 30 s |
| Its memory | `VmRSS` peak 323 MB, 46 MB after the opening |
| A stop during the block | SIGKILL 60 s into it left version 5; the restart compared the one copy for 213 s, reused it, wrote no second one |
| A stop during the reclaim | SIGKILL left version 15 at 7.8 GB; the restart compacted it to 277 MB |
| SQLite's temporary files | a peak of 0.54 GB beside 8.13 GB of files, so at most 8.7 GB against 15.3 GB reserved; measured on a tmpfs, since a free-space drop on btrfs is not usable with reflinked copies (17 GB for 8 GB real) |
| The synthetic catalog (402 MB, 1 000 000 distinct observations), on a tmpfs | 1.5 times the catalog: refused before the copy, version 5; 3.05 times: refused during migration 7, version 5; the migration's RSS peaked at 396 MB, 90 MB after |
| `merge --into` beside a writer | refused in 0.24 s, no write lost (block 60's report) |

## Accepted limits

The spec's section 6, plus:

- **A merge's reopen after a block can be refused** when another process opens the destination in the instant
  between the close and the reopen (block 60): the destination stays migrated and consistent, its copy kept, its
  reclaim left to the next opening.
- **The reclaim's out-of-space line is shown by no test of the gate** (finding 5): a `VACUUM` never grows the file,
  so `max_page_count` cannot make it fail; only a sized tmpfs does (`docs/contributing/testing.md`, section 6).

## For lot 7 (the operator pages, umbrella D19)

The spec's section 6 lists what the pages must say; the blocks found these stale passages and figures:

- `docs/limits.md`: `0009` vacuuming and the per-migration timings; the quote of `migration 7: applying` alone; the
  paragraph "Celui de Docker" and the table's "Fichiers temporaires" column (the temporary files now under `/data`);
  the hardening paragraph (no `read_only:`) still holds, now with the files on `/data`. The first start's figures:
  the Wrap's rows above.
- `docs/troubleshooting-start.md`: the byte message and `MigrationError: migration N failed: database or disk is
  full`; the `database or disk is full` entry sends the operator to check both disks; the new lines: space
  (`Out of disk space, refusing to start: ...`), a held catalog (`Database in use, refusing to start: <path> is held
  by another process`), a refused value naming its call.
- `docs/operate.md`: `merge --into` with the node stopped.
- The migration guide: the copy's share runs ahead of its time, since `VACUUM INTO` writes the tables before building
  the indexes: 68 % at 30 s, 75 % at 90 s, 91 % at 150 s of a 178 s copy (`wrap_kill1.log`).

## The lot's counts

- Fix-backs: 2 (block 10, run 42359879136 cancelled by 42360225043; block 20, run 42361713620 cancelled by
  42361966386).
- Cascaded rebases: 0, both fix-backs having landed before any block above existed.
- Runs re-triggered by them: 2, fewer than the lot's 11 blocks; one more run cancelled by a docs-only push (block 70,
  42383551762).
- Rebases onto `main`: by the lead, after the closing blocks.
- Splits: 3 (20 into 20 and 25, 40 into 40 and 45, the closing block into 75 and 80). Class 2 questions: 1 (block
  40, SQLite's temporary files). Bodies the operator called unreadable: none so far.

## Pitfalls learned

- **`max_page_count` cannot make a `VACUUM` fail**: a reclaim never grows the file, so the reclaim's `SQLITE_FULL`
  is unreachable in a unit test; only a sized tmpfs shows its line. `unshare -rm` mounts one without elevated rights
  on this host.
- **SQLite's temporary files** went to the container's `/var/tmp` until block 45: a full `/var/tmp` failed a
  migration with `SQLITE_FULL` while `/data` had room (proven with a 256 KB tmpfs as `SQLITE_TMPDIR`).
- **A free-space drop on btrfs misleads with reflinked copies**: 17 GB for 8 GB really written; measure on a tmpfs.
- **A bare `PRAGMA locking_mode=EXCLUSIVE` reaches every database attached later**: a read-only source then fails
  `disk I/O error`, or `database is locked` beside a writer. Always `main.`.
- **Ticking a fake inside a long SQLite step**: from a `tick()` SQL function a migration script calls,
  deterministic; inside a `VACUUM`, which calls no function, from a progress handler at every instruction
  (`database_opener_ticked_by_progress`), which ticks many times, so assert the first lines. `PRAGMA cache_size=1`
  spills a `VACUUM INTO` to its file while it is written.
- **The gap between a close and a reopen** is reached by a function registered on the first connection whose
  `weakref.finalize` opens a reader: SQLite releases a closed connection's functions after its file.
- **A test opening a reader SQLite refuses must close it**: `open_reader` returns before the first access fails, and
  the leak surfaced as `ResourceWarning` failures in unrelated later tests.
- **SQLite forwards only "user-defined function raised exception"** for a Python SQL function that raises; the
  function's own error must be kept beside it.
- **`ENOTSUP` and `EOPNOTSUPP` are the same number on Linux**.
- **`functools._lru_cache_wrapper` cannot be subscripted at runtime**: a lazily evaluated `type Memo = ...`.
- **The no-dynamic-attribute rule bans `getattr` even in tests**: `malloc_trim` is looked up with
  `c_library["malloc_trim"]`; a test's C library returns a `ctypes.CFUNCTYPE` around a Python callable, `cast` to
  `ctypes._NamedFuncPointer`.
- **`collections.abc.Callable` is banned** (`TID251`): a callback `Protocol`, generic when its return varies.
- **A mutation reverted with `cp` within the same second at the same size** leaves a stale `.pyc` Python trusts:
  delete `__pycache__` after such a revert.
- **`pkill -f <pattern>` from a Bash tool call matches the calling shell too**: kill by pid.
- **The file bound is strict**: 20 files passes it, and a closing block's records do not count, so its code fixes
  alone can split it.

## Not validated

- The rc row: the crawler's resident memory after the first start, under 150 MB on the operator's node.
- The image's SQLite 3.46.1 (the host runs 3.49.1): the reopen's pragmas, the exclusive lock, the refusal lines
  inside the image under Docker, the crawl's held-catalog line included.
- The reclaim's 30 s lines at full scale: the Wrap's reclaim took 5 s, under one period, and ran before block 80.
- The reclaim's out-of-space line: no run, not even the Wrap's tmpfs ones, ran out of space during the reclaim.
- `SQLITE_TMPDIR=/data` in the compose smoke: run by continuous integration only, never watched failing.
- A real filesystem refusing hard links: the rename path is proven with an injected link raising `EPERM`, `ENOTSUP`
  and `EOPNOTSUPP` only.
- A refused value named on real data: no released catalog holds a value a migration's function refuses.

## Next step

The lead rebases the stack onto `main` and waits for every run to be green; the operator reads the stack and merges
it. No release: v5 ships after lots 3 to 7 and the release candidates, as `BACKLOG.md`'s "v5 release readiness"
entry, which stays, says. The next lot is one of 3 to 6, chosen with the operator.

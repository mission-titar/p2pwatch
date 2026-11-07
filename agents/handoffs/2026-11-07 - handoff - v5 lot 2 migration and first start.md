# Handoff: v5 lot 2, the migration and the first start (tier Spec)

Drafted by block 70's teammate from the block reports, for the closing block (80) to correct. Spec:
`agents/specs/2026-11-06-v5-migration-and-first-start.md`, lot 2 of `agents/specs/2026-11-04-v5-release-readiness.md`.

## Current state

- **A start's migrations are one transaction** (D1): `_apply_migrations` runs `BEGIN`, every pending script, writes
  `PRAGMA user_version` once, then `COMMIT`; any failure or kill leaves the database at its starting version, and the
  next start finds `pre-<first pending>`, compares it and reuses it. A script that closes the transaction is still
  refused, naming its migration. The `-- migration: no-transaction` directive is gone and refused as an unknown one;
  `catalog/0009_vacuum.sql` holds only a comment.
- **The opening reclaims** (D2): after any block of migrations, and at any opening where a quarter of the file or more
  is free pages, `VACUUM` then `wal_checkpoint(TRUNCATE)`, outside any transaction, under `temp_store=FILE`.
- **The opening's order** (D5): the copy, the block, then, when migrations were applied, the connection closed and
  opened again through `_connect` (the memo, the page cache and the scripts' pragmas dropped), the reclaim on the new
  connection, `iso_to_micros` removed, then `MemoryReleaser.release()` once. `GlibcMemoryReleaser` calls
  `malloc_trim(0)` through `ctypes`, a no-op without it. The memoized SQL functions keep at most 65 536 entries.
- **The start reports its long steps** (D3) through the driven port `Ticker`, a clock adapter
  (`ThreadingTicker`, a thread of its own, since the opening holds the event loop): the copy (its size, then every
  30 s the GB written and the share), the comparison with an earlier copy (every 30 s the elapsed time), an interrupted
  copy found and deleted, the block (from which version to which, then every 30 s the migration running), the reclaim
  (the GB and the share of the file it gives back). Each says a stop now costs only the time spent.
- **Short of space, one line in GB** (D1, D3): the domain's `OutOfSpaceError`, raised by the copier's check before
  the copy (needed, free, to free, rounded up) and by the opener on `SQLITE_FULL` during the block or the reclaim
  (free only, measured once the WAL is emptied), with the database's state. The crawl prints it as one line, exit 1;
  `merge` as its one `Merge failed` line, exit 2. The image sets `SQLITE_TMPDIR=/data`, so SQLite's temporary files
  land on the disk the check measures.
- **A merge refuses a held destination** (D4): the destination is opened with `PRAGMA main.locking_mode=EXCLUSIVE`
  and no busy wait, the reopen after a block included; another connection, even idle, makes it fail as
  `HeldDatabaseError`, then `Merge failed: destination <path> is held by another process: stop the node first`.
  Sources keep their read-only attach, so `merge --output` reads a running node's catalog. Any connection meeting
  `SQLITE_BUSY` at its first access now raises `HeldDatabaseError`.
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
| 80 | | closing | |

- **Block 20 was split for the size bound** into 20 and 25: with the comparison's lines it came to 519 lines; they
  moved to block 25, applied there test half first. Block 20 also had one fix-back: size-driven compromises undone,
  which is what took it past the bound and caused the split.
- **Block 40 was split for the file bound** into 40 and 45: block 45 holds the image's `SQLITE_TMPDIR=/data`, the
  operator's option (b) on a class 2 question raised in block 40.
- **Block 10 had one fix-back**: the word "stamp" for writing the schema version, which the operator rejects; it reads
  "written".
- Departures, from the block reports (for the closing block to mark `(Corrected: ...)` in the spec where they change
  a claim):
  - Block 10: `temp_store=FILE` spans the reclaim as well as the block; the `no-transaction` refusal is tested in
    `test_migration_scripts.py`; `test_migration_0009.py` deleted with its `tests_without_unit` entry; a failure at
    the commit names `the commit at version <N>`, at `BEGIN` `the block's start`. Its `SQLITE_FULL` subclass of
    `MigrationError` was replaced in block 40 by the domain's `OutOfSpaceError`.
  - Block 20: `ThreadingTicker` takes a `MonotonicClock` for the elapsed time it passes; `TickerContract` has an
    abstract hook `let_periods_pass`; only the `.partial` gets the "interrupted" line, its `-journal` deleted silently.
  - Block 30: the reclaim's line gives the share of the file beside the GB; it says a stop costs only the time spent
    too. The GB formatting moved to a module of its own, then to the domain in block 40.
  - Block 40: after a `SQLITE_FULL` the line gives no "to free", the need being unknown (the lead confirmed that
    reading of "the GB needed when known"); the opener takes the free-bytes meter; `gigabytes_rounded_up` is new.
  - Block 45: the reserve (the copy plus the file's size again) must now also hold SQLite's temporary files, which
    appendix C's 8.1 GB peak did not count; the Wrap's "reserve only" row settles whether it suffices.
  - Block 50: the reopen comes before the reclaim, not after it (the spec's appendix A, block 50, has the migrations,
    the reclaim, then the reopen): the `VACUUM` gets the build's pragmas with no restore code, and block 10's restore
    of `secure_delete` and `cache_size` is deleted. `MemoryReleaser` has a contract; the memo's seam is
    `create_memoized_function`'s return value, and the opener's test proves the connection is a new one.
  - Block 60: `SQLITE_BUSY` at a first access raises `HeldDatabaseError` in every mode, so a crawler started during
    a merge fails, after its 5 s busy wait, with `<path> is held by another connection`; `_BUSY_TIMEOUT_SECONDS = 5.0`
    spelled out; a reopen held in the instant after the close refuses (the database then migrated, its copy kept, its
    reclaim replayed by the next opening), since SQLite cannot hand an exclusive lock between connections. Its tests
    sit in `test_sqlite_database_opener_exclusive.py`.
  - Block 70: the failed call is kept by a `SqlFunctionFailures` the opening creates and hands to
    `register_sql_functions`; the whole argument list is cut to 100 characters, then `...`. The spec says `local/0010`'s
    `UPDATE` "can never match": code of 2026-10-10 to 2026-10-13, never released, wrote `channel_backoff` again after
    `local/0006`, so a development `local.db` at 6 to 9 could hold it; `local/0011` drops `scheduler_state` whole, so
    the outcome is the same either way. Its test of the key's rename is deleted. The link path's taken name keeps its
    existing test; the rename path's is new.

## The holistic review's findings and their exits

To fill at the closing block.

## Accepted limits

The spec's section 6, plus:

- **A merge's reopen after a block can be refused** when another process opens the destination in the instant
  between the close and the reopen (block 60): the destination stays migrated and consistent, its copy kept, its
  reclaim left to the next opening.

## For lot 7 (the operator pages, umbrella D19)

The spec's section 6 lists what the pages must say; the blocks found these stale passages:

- `docs/limits.md`: `0009` vacuuming and the per-migration timings; the quote of `migration 7: applying` alone; the
  paragraph "Celui de Docker" and the table's "Fichiers temporaires" column (the temporary files now under `/data`);
  the hardening paragraph (no `read_only:`) still holds, now with the files on `/data`.
- `docs/troubleshooting-start.md`: the byte message and `MigrationError: migration N failed: database or disk is
  full`; the `database or disk is full` entry sends the operator to check both disks; the new lines (space, a held
  catalog, a refused value naming its call).
- `docs/operate.md`: `merge --into` with the node stopped.

## The lot's counts

To fill at the closing block: fix-backs (blocks 10 and 20 known so far), cascaded rebases, the runs they
re-triggered, rebases onto `main`, bodies the operator called unreadable.

## Pitfalls learned

- **`max_page_count` cannot make a `VACUUM` fail**: a reclaim never grows the file, so the reclaim's `SQLITE_FULL`
  is unreachable in a unit test; only a sized tmpfs shows its line. `unshare -rm` mounts one without elevated rights
  on this host, and can serve the Wrap's "reserve only" row.
- **SQLite's temporary files** went to the container's `/var/tmp` until block 45: a full `/var/tmp` failed a
  migration with `SQLITE_FULL` while `/data` had room (proven with a 256 KB tmpfs as `SQLITE_TMPDIR`).
- **A bare `PRAGMA locking_mode=EXCLUSIVE` reaches every database attached later**: a read-only source then fails
  `disk I/O error`, or `database is locked` beside a writer. Always `main.`.
- **Ticking a fake inside a long SQLite step**: from a progress handler on the connection (it also fires during the
  free-space check's `PRAGMA`s, so check `ticker.periods`), or from a `tick()` SQL function a migration script calls,
  deterministic. `PRAGMA cache_size=1` spills a `VACUUM INTO` to its file while it is written.
- **The gap between a close and a reopen** is reached by a function registered on the first connection whose
  `weakref.finalize` opens a reader: SQLite releases a closed connection's functions after its file.
- **A test opening a reader SQLite refuses must close it**: `open_reader` returns before the first access fails, and
  the leak surfaced as `ResourceWarning` failures in unrelated later tests.
- **SQLite forwards only "user-defined function raised exception"** for a Python SQL function that raises; the
  function's own error must be kept beside it.
- **`ENOTSUP` and `EOPNOTSUPP` are the same number on Linux**.
- **`functools._lru_cache_wrapper` cannot be subscripted at runtime**: a lazily evaluated `type Memo = ...`.
- **The no-dynamic-attribute rule bans `getattr` even in tests**: `malloc_trim` is looked up with
  `c_library["malloc_trim"]`.
- **`collections.abc.Callable` is banned** (`TID251`): a callback `Protocol`, generic when its return varies.
- **A mutation reverted with `cp` within the same second at the same size** leaves a stale `.pyc` Python trusts:
  delete `__pycache__` after such a revert.
- **`pkill -f <pattern>` from a Bash tool call matches the calling shell too**: kill by pid.

## Not validated

- The Wrap's rows (spec section 4, "On a copy of the operator's node and a synthetic catalog"): content by
  `compare.py`, a stop during the migrations and during the reclaim at full scale, a `data/` short of space with
  `SQLITE_TMPDIR=/data`, the first start's log with no gap over 60 s, `merge --into` beside `writer.py`, the
  synthetic catalog on a disk with the reserve only (whether the reserve holds the temporary files too), and its
  resident memory.
- The rc row: the crawler's resident memory after the first start, under 150 MB on the operator's node.
- The image's SQLite 3.46.1 (the host runs 3.49.1): the reopen's pragmas, the exclusive lock, the refusal lines
  inside the image under Docker.
- `SQLITE_TMPDIR=/data` in the compose smoke: run by continuous integration only.
- A real filesystem refusing hard links: the rename path is proven with an injected link raising `EPERM`, `ENOTSUP`
  and `EOPNOTSUPP` only.
- A refused value named on real data: no released catalog holds a value a migration's function refuses.

## Next step

The holistic review over `git diff origin/main...origin/fix/migration-small-findings`, then the closing block (80):
its findings, `BACKLOG.md` reconciled, this handoff corrected and its counts, the umbrella's lot 2 rows marked, the
spec's departures marked `(Corrected: ...)`; the Wrap's measurements by the lead before the review. Then the operator
reads the stack and merges it.

# Handoff: rows read by column name

Drafted by block 50 from the lot's block reports (#548, #549, #551 to #553) and its own, for the closing block 60 to
correct with the holistic review.

## State

Tier Spec lot. Spec `agents/specs/2026-10-29-rows-read-by-column-name.md` (reviewed by `rows-by-name-spec-review`,
approved by the operator 2026-10-29). It ships the first half of the backlog entry "Rows read by column name" (section
7 of `agents/specs/2026-10-28-typed-identifiers.md`); its second half, the round-trip contracts, becomes an entry of
its own, which the closing block adds with the two other `BACKLOG.md` changes of spec section 7.

One stack cut from `main` at `6c6bed0e`, which had not moved when block 50 was written (`git fetch`, 2026-10-29).
Seven blocks against the spec's six: block 10 passed 20 files (22: the estimate missed `test_database_digest.py` and
`pyproject.toml`), so the lead approved its split, the catalog migrations 0002 to 0009 moving to a new block 15.

| Block | Pull request | Branch |
|---|---|---|
| 10 | #548 | `test/rows-helper` |
| 15 | #549 | `test/rows-helper-catalog-migrations` |
| 20 | #551 | `test/rows-helper-stores` |
| 30 | #552 | `test/rows-helper-steps` |
| 40 | #553 | `refactor/local-rows-by-name` |
| 50 | #TBD | `refactor/rows-by-name` |
| 60 | the closing block's pull request | `docs/rows-by-name-wrap` |

Not merged at writing. Nothing the operator sees changes (spec section 2): no page, metric, notification, config key
or schema. The image changes only in how the persistence adapter reads its rows.

## What was built

- **`NamedRow` and `named_row`** (block 10, D1), in `persistence_sqlite/named_row.py`: a `dict` subclass whose
  `__iter__` raises `TypeError` ("a row is read by column name"), and the row factory that builds it from
  `cursor.description`, refusing a column name that appears twice with `ValueError`. `row[0]` raises `KeyError`.
- **`database_digest`** (block 10, D4) reads `user_version` through a cursor of its own carrying the factory: the
  factory's first production caller, and it digests any connection, the pre-migration copier's raw candidate and the
  tests' raw connections included.
- **The tests' helper** (block 10, D5): `rows(connection, sql, parameters)` in
  `tests/support/adapters/driven/persistence_sqlite/named_row.py`, which reads a query on its own cursor carrying the
  factory and returns plain `dict`s, keeping pytest's diff of a failing comparison.
- **The tests read by name** (blocks 10 to 30): the local migration tests (10), the catalog migrations 0002 to 0009
  (15), 0010 to 0015, `last_seen_at`, `drop_verification` and the stores' tests (20), the remaining stores', the
  pre-migration copier's, the read connections', five steps' and `tests/support`'s `catalog_rows` and `older_catalog`
  (30). `helpers.py`'s `rows_without_id` returns dicts, sorted by the exported `sorted_by_values` (20);
  `catalog_rows` gains `count_decisions` (30). Aggregates and `typeof()` take an alias; a query selecting two columns
  of one name aliases them; a query whose result a test sorted gets an `ORDER BY`.
- **local.db** (block 40): `open_local` set the factory; the node id, policy fingerprint, backoff state and tracked
  download stores read by name; `_LATEST_SEEN_AT_BY_FILE` aliases its `COALESCE` as `seen_at_micros`.
- **Every connection** (block 50): the factory moves into `SqliteDatabaseOpener._connect`, set before `_configure`
  reads `journal_mode`, so `open_local`'s line and `older_catalog.open_local_at`'s go; `open_reader` sets it in place
  of `sqlite3.Row`. The catalog's stores (decisions, source points, catalog scan), `observation_read`'s mapper and
  every `PRAGMA` (D2: the opener's, the catalog copier's, the pre-migration copier's) read by name;
  `_COUNT_FILES` aliases `file_count`, `_HAS_POINTS_BEFORE` `has_points`. `sqlite_source_reader.py`'s rows and
  `observation_from_row` are typed `NamedRow`. The SQL console (D3) reads on a cursor of its own whose `row_factory` is
  `None`. `AGENTS.md`'s Persistence row says rows are read by column name; `thread_read_connections.py`'s docstrings
  follow.

## Evidence

Every block's `uv run poe check` exit 0 at its tip (crawler: 1725 passed at block 40, 1726 at block 50, 15
deselected; 100 % branch coverage; `_unit-coverage-check` clean).

Budgets against each parent: block 10, 286 lines and 17 files; block 15, 124 and 5; block 20, 337 and 17; block 30,
311 and 12; block 40, 39 and 7; block 50, 104 and 16 (the handoff and the spec outside the count).

Continuous integration, `gh pr checks <n> --required` (2026-10-29): `validate / gate` passes on #548, #549, #551,
#552 and #553. Block 50's: to be read by the closing block.

Acceptance, at block 50's tip (`cd9fc28b`):

- 1: `test_named_row.py` proves `row[0]` raises `KeyError`, `a, b = row` and `*row` raise `TypeError`, a duplicate
  name `ValueError` (4 tests, passed).
- 2: `test_sqlite_sql_executor.py::test_a_column_name_repeated_keeps_both_columns_in_order`, watched failing before
  D3's cursor: `ValueError: the column 'a' appears twice`.
- 3: each trial applied alone and reverted (tree clean after each), `uv run poe test` in `packages/crawler`, exit 1.
  `sqlite_backoff_state_store.py` put back as tuple unpacking: 6 failed, 1720 passed, `E       TypeError: a row is
  read by column name` at `sqlite_backoff_state_store.py:40`, in the five tests of `test_sqlite_backoff_state_store.py`
  and `test_crawler_composition_wiring.py::test_a_backoff_the_previous_run_saved_holds_the_ed2k_search`.
  `sqlite_node_id_store.py` put back as `row[0]`: 6 failed, 1720 passed, `E       KeyError: 0` at
  `sqlite_node_id_store.py:30`, in both tests of `test_sqlite_node_id_store.py` and four of
  `test_crawler_composition_wiring.py`. Block 40 ran the same trials at its tip with the same counts.
- 4: the corrected command (named_row.py left out, spec section 4) prints nothing, exit 1; under the second trial it
  prints `sqlite_node_id_store.py:30:        return NodeId(row[0]) if row is not None else None`, so it can fail.

Tests watched failing, from the block reports:

- Block 10: `test_unpacking_a_row_raises` against a plain dict subclass, `Failed: DID NOT RAISE TypeError`;
  `test_a_column_name_that_appears_twice_is_refused`, `Failed: DID NOT RAISE ValueError`;
  `test_a_connection_carrying_the_row_factory_has_the_digest_of_a_raw_one`, `KeyError: 0`; the helper's duplicate-name
  test, `Failed: DID NOT RAISE ValueError`; the helper's plain-dict test, `assert {<class 'p2pw...ow.NamedRow'>} ==
  {<class 'dict'>}`.
- Blocks 15 to 30: no new behaviour (the tests' reads move); each verified by a temporary probe setting the factory on
  the connections, reverted: block 15, 21 passed, 18 of 21 failing with the pre-block files; block 20, every failure
  raised in `src` or `tests/support`, and a probe raising only in test modules passed 233 (76 failed, 1 error with the
  pre-block files); block 30, over the whole suite, 189 failures in `src` only, and the test-module probe 3 failed,
  1720 passed (95 failed, 32 errors before), the three explained in #552.
- Block 40: `test_open_local_returns_rows_read_by_column_name`, `isinstance((1,), NamedRow)` false.
- Block 50: `test_open_catalog_returns_rows_read_by_column_name`, `where False = isinstance((1,), NamedRow)`;
  `test_open_reader_reads_seeded_row_by_column_name`, `isinstance(<sqlite3.Row object ...>, NamedRow)` false; with
  the factory on every connection and before any read moved, the existing suite failed in each `src` read, then
  passed once each read went by name; with `open_reader` switched, only the console's tests failed (5, plus
  `test_crawler_composition_wiring.py`'s full-mode test through the console), until D3's cursor.

## Departures from the spec

- Block 10: split into 10 and 15 (State); the factory refuses a duplicate with `ValueError`, the spec saying only
  "raises".
- Block 20: `helpers.py`, row 30's, moved with its only caller's tests; `test_sqlite_decision_store_latest_decisions.py`
  unchanged (it reads only through the store); 337 lines against an estimate of 110, mostly expected rows rewritten as
  dicts.
- Block 30: the "five" step tests are the five whose own reads the control probe found; tests on a raw connection read
  through `rows()` too; `test_thread_read_connections.py`'s factory test keeps its own read.
- Block 40: `older_catalog.open_local_at` set the factory, which block 50 removed once `_connect` carries it.
- Block 50: the pre-migration copier's candidate connection gets no factory, the spec's row naming it: its one read is
  `database_digest`'s, through a cursor of its own (D4), and `iterdump` resets its cursor's factory, so a factory there
  would be a line no test can observe. Acceptance criterion 4 corrected after approval (`(Corrected: ...)` beside it):
  its pathspec leaves `named_row.py` out, whose docstring matched forever (found by block 40).

## Class 1 fixes

- Block 10: `test_local_migration_0013.py` selected `m.name, c.name`, a duplicate name the factory refuses: aliased;
  `test_local_migration_0015.py`'s parameter `rows` renamed `node_runtime`, as it shadowed the helper.
- Block 15: `test_migration_0007.py`'s `rows` parameter renamed `file_observations`; `test_migration_0008.py`'s
  `m.name, p.name` aliased.
- Block 20: `helpers.py`'s `source_variants` read selected `f.native_id, s.native_id`: aliased; `_insert_source_points`'
  `rows` renamed `source_points`; local `rows` and `_rows` in migration tests 0011 to 0014 renamed.
- Blocks 30 to 50: none.

No class 2 question.

## The holistic review

To be written by the closing block.

## Counts

No fix-back and no cascaded rebase so far. 7 blocks against 6 planned. No body called unreadable so far.

## Pitfalls

- mypy refuses `row[0]` on a value typed `NamedRow`, but a row from `execute` is `Any`: only the run-time error guards
  the production reads (block 10).
- A query returning no row never calls the row factory, so a duplicate column name in it goes unrefused until a row
  comes back (block 15).
- `PRAGMA foreign_key_check` compared with `[]` holds under any factory, since it returns no row (block 20).
- A cursor's factory overrides its connection's: the helper `rows()` and the console's cursor rely on it; an
  `iterdump` resets its cursor's factory (spec appendix A).
- `iter_latest_observations` returns a lazy `map` over the cursor, so a test's `list()` drives `src`'s mapper: a probe
  telling a test's read from `src`'s takes that one for the test's (block 30).
- `INSERT ... RETURNING` reads through `rows()` like a `SELECT`; `content_hash(*variant.values())` needs the expected
  variant typed `dict[str, Any]` (block 30).
- A connection opened through `SqliteDatabaseOpener.open` directly (the support's `open_*_at`) carries the factory
  only since block 50.
- `Cursor.execute`, like `Connection.execute`, runs one statement only: the console's single-statement guard holds on
  its own cursor (block 50, the module docstring updated).

## Not validated

- A column written in the wrong order, or aliased under another's name, is still caught only by a test giving both
  columns distinct values (spec section 7): `duration_seconds` and `bitrate_kbps` swapped by alias in
  `_SQL_LIST_FILES_BASE` passed on `main`. The "Round-trip contracts" entry carries it.
- The integration suites run only in CI's `validate / gate`.
- No real node has run the factory: the reads of a large catalog by name, and the console on it.

## Next

A release is the operator's decision after the stack merges; the v5 waits for a P2P network other than eD2k
(operator, 2026-10-27). Then `BACKLOG.md`, read before proposing.

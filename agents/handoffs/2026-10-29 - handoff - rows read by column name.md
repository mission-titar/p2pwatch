# Handoff: rows read by column name

Drafted by block 50 from the lot's block reports (#548, #549, #551 to #553) and its own, corrected by the closing
block 60 with the holistic review and block 55's report (#555).

## State

Tier Spec lot. Spec `agents/specs/2026-10-29-rows-read-by-column-name.md`, approved by the operator 2026-10-29. It
ships the first half of the backlog entry "Rows read by column name" (section 7 of
`agents/specs/2026-10-28-typed-identifiers.md`); its second half, the round-trip contracts, becomes an entry of its
own, which the closing block adds with the two other `BACKLOG.md` changes of spec section 7.

How the spec was made, all on 2026-10-29:

- **The surveys**: `rows-by-name-inventory` found the positional reads and the connections (spec appendix A);
  `rows-by-name-estimates` (Sonnet) measured the block table's estimates and probed the tests' reads with a spying
  dict factory.
- **The first review pass**, by `rows-by-name-spec-review` (`.reviews/rows-by-name-spec.md`), on a draft holding both
  halves of the backlog entry: CRITICAL 1, MAJOR 7, MINOR 9. Its CRITICAL: under a plain `dict` factory, unpacking a
  row yields its column names silently, against the draft's claim; `NamedRow`'s raising `__iter__` closes it. Its
  trials found that today's tests already catch all but one of about 110 column swaps.
- **The scope cut to option B, decided by the operator**: the round-trip tests left the lot (D6), since drawn values
  would add almost no detection; appendix B keeps what the Discuss settled for them.
- **The second review pass**, on the cut spec: CRITICAL 0, MAJOR 2, MINOR 8, all closed before approval
  (criterion 4's pathspec restricted to `*.py`, `NamedRow` landing in block 10 with `database_digest` as its first
  caller, the helper returning plain `dict`s, the catalog's switch split from local.db's into blocks 40 and 50,
  appendix B's values a draw must avoid).

One stack cut from `main` at `6c6bed0e`, which had not moved when block 60 was written (`git fetch`, 2026-10-29).
Eight blocks against the spec's six, the closing one included: block 10 passed 20 files (22: the estimate missed
`test_database_digest.py` and `pyproject.toml`), so the lead approved its split, the catalog migrations 0002 to 0009
moving to a new block 15; block 55 was cut from the holistic review's three code findings, so it is not in the spec's
table.

| Block | Pull request | Branch |
|---|---|---|
| 10 | #548 | `test/rows-helper` |
| 15 | #549 | `test/rows-helper-catalog-migrations` |
| 20 | #551 | `test/rows-helper-stores` |
| 30 | #552 | `test/rows-helper-steps` |
| 40 | #553 | `refactor/local-rows-by-name` |
| 50 | #554 | `refactor/rows-by-name` |
| 55 | #555 | `refactor/rows-by-name-findings` |
| 60 | this block's pull request | `docs/rows-by-name-wrap` |

Not merged at writing. Nothing the operator sees changes (spec section 2): no page, metric, notification, config key
or schema. The image changes in how the persistence adapter reads its rows.

## What was built

- **`NamedRow` and `named_row`** (block 10, D1), in `persistence_sqlite/named_row.py`: a `dict` subclass whose
  `__iter__` raises `TypeError` ("a row is read by column name"), and the row factory that builds it from
  `cursor.description`, refusing a column name that appears twice with `ValueError`. `row[0]` raises `KeyError`.
- **`database_digest`** (block 10, D4) reads `user_version` through a cursor of its own carrying the factory: the
  factory's first production caller, and it digests any connection, the pre-migration copier's candidate and the
  tests' raw connections included.
- **The tests' helper** (block 10, D5): `rows(connection, sql, parameters)` in
  `tests/support/adapters/driven/persistence_sqlite/named_row.py`, which reads a query on its own cursor carrying the
  factory and returns plain `dict`s, keeping pytest's diff of a failing comparison.
- **The tests read by name** (blocks 10 to 30, 55): the local migration tests (10), the catalog migrations 0002 to
  0009 (15), 0010 to 0015, `last_seen_at`, `drop_verification` and the stores' tests (20), the remaining stores', the
  pre-migration copier's, the read connections', five steps' and `tests/support`'s `catalog_rows` and `older_catalog`
  (30), the SQL functions' tests, `test_variants.py` and `test_micros.py` (55). `helpers.py`'s `rows_without_id`
  returns dicts, sorted by the exported `sorted_by_values` (20); `catalog_rows` gains `count_decisions` (30).
  Aggregates and `typeof()` take an alias; a query selecting two columns of one name aliases them; a query whose
  result a test sorted gets an `ORDER BY`.
- **local.db** (block 40): `open_local` set the factory; the node id, policy fingerprint, backoff state and tracked
  download stores read by name; `_LATEST_SEEN_AT_BY_FILE` aliases its `COALESCE` as `seen_at_micros`.
- **Every connection** (blocks 50, 55): the factory moves into `SqliteDatabaseOpener._connect`, set before
  `_configure` reads `journal_mode`, so `open_local`'s line and `older_catalog.open_local_at`'s go; `open_reader` sets
  it in place of `sqlite3.Row`; the pre-migration copier's candidate carries it (55). The catalog's stores (decisions,
  source points, catalog scan), `observation_read`'s mapper and every `PRAGMA` (D2: the opener's, the catalog
  copier's, the pre-migration copier's) read by name; `_COUNT_FILES` aliases `file_count`, `_HAS_POINTS_BEFORE`
  `has_points`. `sqlite_source_reader.py`'s rows and `observation_from_row` are typed `NamedRow`. The SQL console
  (D3) reads on a cursor of its own whose `row_factory` is `None`. `AGENTS.md`'s Persistence row says rows are read by
  column name; `thread_read_connections.py`'s docstrings follow.
- **The compose smoke's read script** (block 55), run by the image's own Python where the tests' helper is not
  importable: it sets `sqlite3.Row` and reads `state` and an aliased `completed`.
- **`BACKLOG.md`** (block 60): spec section 7's three changes.

## Evidence

Every block's `uv run poe check` exit 0 at its tip (crawler: 1724 passed at block 40, 1726 at blocks 50 to 60, 15
deselected; 100 % branch coverage; `_unit-coverage-check` clean).

Budgets against each parent: block 10, 286 lines and 17 files; block 15, 124 and 5; block 20, 337 and 17; block 30,
311 and 12; block 40, 39 and 7; block 50, 104 and 16 (the handoff and the spec outside the count); block 55, 33 and
4; block 60, 14 and 1 (`BACKLOG.md`; the handoff outside the count).

Continuous integration, `gh pr checks <n> --required` (2026-10-29): `validate / gate` passes on #548, #549, #551,
#552, #553, #554, #555 (run 40854481618) and #556 (run 40855061815), each on its first attempt. #556's run after
its fix-back (Counts) is the lead's to read.

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
  `test_crawler_composition_wiring.py`. Block 40 ran the same trials at its tip: 6 failed, 1718 passed, the same lines
  failing.
- 4: the corrected command (named_row.py left out, spec section 4) prints nothing, exit 1; under the second trial it
  prints `sqlite_node_id_store.py:30:        return NodeId(row[0]) if row is not None else None`, so it can fail.
  The holistic review re-ran it at block 50's top: nothing, exit 1.

Tests watched failing, and probes, from the block reports:

- Block 10: `test_unpacking_a_row_raises` against a plain dict subclass, `Failed: DID NOT RAISE TypeError`;
  `test_a_column_name_that_appears_twice_is_refused`, `Failed: DID NOT RAISE ValueError`;
  `test_a_connection_carrying_the_row_factory_has_the_digest_of_a_raw_one`, `KeyError: 0`; the helper's duplicate-name
  test, `Failed: DID NOT RAISE ValueError`; the helper's plain-dict test, `assert {<class 'p2pw...ow.NamedRow'>} ==
  {<class 'dict'>}`. A temporary probe (reverted) set the factory on `open_local_at`'s connection: the local migration
  tests passed under it (23 passed), 0009 left out since its read goes through `SqlitePolicyFingerprintStore`,
  block 40's.
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
- Block 55: no test discriminates the candidate's factory: with the line and its import removed, the crawler's suite
  gives 1726 passed, since the candidate's only read is `database_digest`'s own cursor. The smoke's read script,
  `exec`'d against a scratch `local.db` holding a completed and a downloading row, printed `completed True` and
  `downloading False`; the `compose_integration` suite itself runs in CI only. At its tip, criterion 4's regex over
  `packages/crawler/**/*.py`, tests included, prints only `named_row.py`'s docstring, `test_named_row.py`'s two tests
  that a positional read raises, and `**row` dict spreads (five migration tests, `helpers.py`).
- The holistic review: a pytest plugin wrapping `NamedRow.__getitem__` over the crawler's suite (1726 passed) saw
  every one of the 109 `row["..."]` sites under `persistence_sqlite` read at least once, so each by-name read meets a
  test. The factory costs 2.6 µs a row against 1.06 for `sqlite3.Row` and 1.0 for tuples (100,000 rows of 11
  columns): about 0.15 s more on a reevaluation of 100,000 files.

## Departures from the spec

- Block 10: split into 10 and 15 (State); the factory refuses a duplicate with `ValueError`, the spec saying only
  "raises".
- Block 15: `test_migration_0002.py` tests local.db through `open_local`, kept in 15 as the spec's range "0002 to
  0009" names it.
- Block 20: `helpers.py`, row 30's, moved with its only caller's tests; `test_sqlite_decision_store_latest_decisions.py`
  unchanged (it reads only through the store); 337 lines against an estimate of 110, mostly expected rows rewritten as
  dicts.
- Block 30: the "five" step tests are the five whose own reads the control probe found; `test_search_task_runner.py`
  and `test_source_watcher.py` failed there only through `catalog_rows` and change nothing; `catalog_rows`'
  `decision_tiers` keeps its return type, since its callers compare pairs or pass them to `dict()`; tests on a raw
  connection read through `rows()` too; `test_thread_read_connections.py`'s factory test keeps its own read.
- Block 40: `older_catalog.open_local_at` set the factory, which block 50 removed once `_connect` carries it.
- Block 50: the pre-migration copier's candidate connection got no factory, the spec's row naming it; block 55
  added it, so D1 and row 50 hold. Acceptance criterion 4 corrected after approval (`(Corrected: ...)` beside it):
  its pathspec leaves `named_row.py` out, whose docstring matched forever (found by block 40).
- Block 55: not in the spec's table (State); `test_variants.py`'s function-list test sorts by an `ORDER BY name`, as
  blocks 10 to 30 did.

## Class 1 fixes

- Block 10: `test_local_migration_0013.py` selected `m.name, c.name`, a duplicate name the factory refuses: aliased;
  `test_local_migration_0015.py`'s parameter `rows` renamed `node_runtime`, as it shadowed the helper.
- Block 15: `test_migration_0007.py`'s `rows` parameter renamed `file_observations`; `test_migration_0008.py`'s
  `m.name, p.name` aliased.
- Block 20: `helpers.py`'s `source_variants` read selected `f.native_id, s.native_id`: aliased; `_insert_source_points`'
  `rows` renamed `source_points`; local `rows` and `_rows` in migration tests 0011 to 0014 renamed.
- Blocks 30 and 40: none.
- Block 50: the console module's docstring named `Connection.execute` as the single-statement guard; it now names
  `Cursor.execute`, which refuses a second statement the same way.
- Block 55: none.

No class 2 question.

## The holistic review

By `rows-holistic-review` over `git diff origin/main...origin/refactor/rows-by-name` (blocks 10 to 50),
`.reviews/rows-by-name-holistic.md`: CRITICAL 0, MAJOR 0, MINOR 6. Spec conformance clean apart from the first
finding: D1 to D6, criteria 1 to 4 (3 taken from the reports), criterion 4's `(Corrected: ...)`, section 6's
documents.

| Finding | Exit |
|---|---|
| The pre-migration copier's candidate was the one connection without the factory, against D1 and row 50, with no `(Corrected: ...)` | fixed, block 55: the candidate carries the factory; no test discriminates the line (Evidence) |
| Seven positional reads left in `test_variants.py` and `test_micros.py`, on raw connections testing the SQL functions, which the inventory's probe never saw | fixed, block 55: read through `rows()`, each expression aliased |
| `test_compose_smoke.py`'s `_READ_ROW` script read `row[0], bool(row[1])` | fixed, block 55: `sqlite3.Row`, `state` and an aliased `completed` |
| The draft's test counts at block 40 (1725, "the same counts") contradicted block 40's report (1718 passed in each trial) | fixed, block 60: Evidence |
| The draft said "Blocks 30 to 50: none" under Class 1 fixes, losing block 50's docstring fix | fixed, block 60: Class 1 fixes |
| The draft lost five notes of the reports: (a) the dict keys of a migration test across a column rename, (b) block 10's probe, (c) block 15's `test_migration_0002.py`, (d) `test_sqlite_catalog_file_reader.py`'s locals named `rows`, (e) block 30's unchanged step tests and `decision_tiers` | fixed, block 60: (a) and (d) in Pitfalls, (b) in Evidence, (c) and (e) in Departures |

## Counts

One fix-back, of the closing block: its handoff's CI line, written while #555's run was pending, updated once
#555 and #556 passed; the push re-triggered #556's run only. No cascaded rebase. Eight blocks against six planned,
the closing one included: block 10 split into 10 and 15, block 55 cut from the holistic review. No body called
unreadable so far.

## Pitfalls

- mypy refuses `row[0]` on a value typed `NamedRow`, but a row from `execute` is `Any`: only the run-time error guards
  the production reads (block 10).
- A migration test comparing a table before and after a column rename maps the old keys to the new ones, since the
  rows are dicts (block 10).
- A query returning no row never calls the row factory, so a duplicate column name in it goes unrefused until a row
  comes back (block 15).
- `PRAGMA foreign_key_check` compared with `[]` holds under any factory, since it returns no row (block 20).
- `test_sqlite_catalog_file_reader.py` keeps many locals named `rows` holding `CatalogEntry` tuples, in functions that
  never call the helper: a name beside `rows()` that a later edit can trip on (block 20).
- A cursor's factory overrides its connection's: the helper `rows()`, `database_digest` and the console's cursor rely
  on it; `iterdump` resets its cursor's factory (spec appendix A).
- `iter_latest_observations` returns a lazy `map` over the cursor, so a test's `list()` drives `src`'s mapper: a probe
  telling a test's read from `src`'s takes that one for the test's (block 30).
- `INSERT ... RETURNING` reads through `rows()` like a `SELECT`; `content_hash(*variant.values())` needs the expected
  variant typed `dict[str, Any]` (block 30).
- `Cursor.execute`, like `Connection.execute`, runs one statement only: the console's single-statement guard holds on
  its own cursor (block 50).
- Criterion 4's regex matches `**row`, a dict spread, too: run over the tests, its output is no count of positional
  reads (block 55).

## Not validated

- A column written in the wrong order, or aliased under another's name, is still caught only by a test giving both
  columns distinct values (spec section 7): `duration_seconds` and `bitrate_kbps` swapped by alias in
  `_SQL_LIST_FILES_BASE` passed on `main`. The "Round-trip contracts" entry carries it.
- No test fails without the pre-migration copier's candidate factory (block 55): it guards a read not yet written.
- The integration suites run only in CI's `validate / gate`; the smoke's read script ran locally only on a scratch
  `local.db`.
- No real node has run the factory: the reads of a large catalog by name, and the console on it. The holistic review's
  measure puts the cost at about 0.15 s more per 100,000 files read.

## Next

The lot changes the image: the crawler reads its rows by column name. Whether a release follows is the lead's to
propose once the stack merges (Wrap f), under the constraint the previous handoff names: the v5 waits for a P2P
network other than eD2k (operator, 2026-10-27). Then `BACKLOG.md`, read before proposing.

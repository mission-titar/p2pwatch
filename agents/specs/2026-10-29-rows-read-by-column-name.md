# Rows read by column name

Tier Spec. Discussed with the operator on 2026-10-29. Ships the first half of the `BACKLOG.md` entry "Rows read by
column name" (section 7 of `agents/specs/2026-10-28-typed-identifiers.md`); its second half, the round-trip tests,
becomes an entry of its own (section 7).

## 1. In short

An SQLite row is `Any` to mypy. A store that reads a column by its index, or unpacks a row into names, maps the wrong
column without any check seeing it. Every row the persistence adapter reads becomes a `NamedRow`, which only a
column's name can read: a read by index or by unpacking raises, so it fails the first test that runs it.

## 2. What the operator will see

Nothing: no page, metric, notification, config key or schema changes. The SQL console answers as before.

## 3. Decisions

- **D1. One row factory on every connection the persistence adapter opens, returning a `NamedRow`**: a `dict`
  subclass, built from `cursor.description`, whose `__iter__` raises `TypeError`; the factory raises on a column
  name that appears twice. Both live in `persistence_sqlite/named_row.py`. *`row[0]` raises `KeyError`, and
  `a, b = row`, `*row` or `for a, b in rows` raise `TypeError`, so each fails the first test that runs it, and the
  gate's 100 % coverage runs every read. A plain `dict` would hand an unpacking its keys silently, and keep one of two
  equal names silently. `row["a"]`, `row == {...}`, `dict(row)` and `.items()` still work (probed by
  `rows-by-name-spec-review`). An ast-grep rule on `row[<int>]` would not see unpacking (operator: enforce by design,
  2026-10-29).*
- **D2. A `PRAGMA` is read by its column name** (`["user_version"]`). *D1 leaves no index read.*
- **D3. The SQL console keeps positional rows through its own cursor**: `cursor = connection.cursor()`,
  `cursor.row_factory = None`, on the connection `open_reader` gives it. *An arbitrary query may repeat a name
  (`SELECT 1 AS a, 2 AS a`) and the console shows columns in order; the console needs `open_reader`'s read-only
  guards more than any reader, so it keeps them (operator, 2026-10-29). Probed on Python 3.13: such a cursor returns
  `[(1, 2)]` while the connection returns dicts.*
- **D4. `database_digest` reads through its own cursor carrying D1's factory.** *It digests whatever connection it is
  given, the pre-migration copier's raw candidate and the tests' raw connections included; it is also the factory's
  first production caller, so block 10 can land `named_row.py` without `dead-code-check` refusing it.*
- **D5. Tests read rows through one support helper**, `rows(connection, sql, parameters)` in
  `tests/support/adapters/driven/persistence_sqlite/named_row.py`, which runs the query on its own cursor carrying
  D1's factory and returns plain `dict`s. *A cursor's factory overrides its connection's, so the tests move to names
  in blocks under 20 files each before any connection changes (`rows-by-name-estimates`). Once every connection
  carries the factory, the helper keeps two roles: it reads a test's own raw connection (a migration test's, the
  digest's) the same way, and its plain `dict`s keep pytest's diff on a failing comparison, which a `NamedRow` loses
  ("faulty `__repr__`", probed): pytest's representation iterates the row.*
- **D6. The round-trip tests leave this lot** (operator, 2026-10-29). *Of about 110 column swaps tried on `main`, the
  tests already catch all but one (`rows-by-name-spec-review`): drawn values in new contracts would add almost no
  detection. Their value is each port's promise written as a contract, which deserves its own Discuss and its own
  place among the priorities. Appendix B keeps what this Discuss settled for them.*

## 4. Acceptance

1. In `persistence_sqlite`'s `src`, no row is read by index or by unpacking, the console aside: `NamedRow`'s own test
   proves that `row[0]`, `a, b = row` and `*row` raise, and the factory's that a duplicate name is refused.
2. The console answers `SELECT 1 AS a, 2 AS a` with the columns `("a", "a")` and the rows `(("1", "2"),)`, a test
   watched failing without D3's cursor.
3. Two trials, each applied alone at block 50's tip, fail `uv run poe test` in the crawler, the failure line recorded
   in its report: `sqlite_backoff_state_store.py`'s read put back as tuple unpacking (`for client_name, channel, ...
   in rows`); `sqlite_node_id_store.py`'s read put back as `row[0]`.
4. `git grep -nE 'row\[[0-9]+\]|fetchone\(\)\[[0-9]+\]|\*row\b' -- 'packages/crawler/src/**/*.py'` prints nothing.
   It sees only an index read on a name `row` or on `fetchone()`, and `*row`; criterion 1 covers the rest.

## 5. Blocks

Estimates by `rows-by-name-estimates` (Sonnet, 2026-10-29), within about 25 %; the split of its block 40 follows
`rows-by-name-spec-review`'s count of about 21 files. The bound is checked after committing.

| # | Branch | Holds | Lines, files |
|---|---|---|---|
| 10 | `test/rows-helper` | `named_row.py` and its test; D4; D5's helper and its test; the local migration tests and catalog migrations 0002 to 0009 adopt it | 170, 19 |
| 20 | `test/rows-helper-stores` | catalog migrations 0010 to 0015, `last_seen_at`, `drop_verification`; the tests of `append_only`, `observation_read`, `backoff`, `catalog_copier`, `catalog_file_reader`, `database_opener`, `decision_store`, `node_id` | 110, 17 |
| 30 | `test/rows-helper-steps` | the tests of `observation_store`, `pre_migration_copier`, `source_point_store_writer`, `tracked_download_store`, `thread_read_connections`, the five of `tests/application/steps`, and `tests/support`'s `helpers`, `older_catalog`, `catalog_rows` | 110, 15 |
| 40 | `refactor/local-rows-by-name` | `open_local` sets the factory; local.db's stores (`NodeId`, `PolicyFingerprint`, `BackoffState`, `TrackedDownload`) read by name | 100, 8 |
| 50 | `refactor/rows-by-name` | the factory moves into `_connect`, set before `_configure` reads `journal_mode`, and onto `open_reader` and the pre-migration copier's candidate; the catalog's stores, `observation_read` and every `PRAGMA` by name (D2); the console's cursor (D3); `AGENTS.md`; drafts the handoff | 220, 14 |
| 60 | `docs/rows-by-name-wrap` | closing: the holistic findings, `BACKLOG.md`, the handoff | |

The order: the tests first, on the helper, so blocks 40 and 50 change the connections and the `src` alone; local.db,
the smaller, before the catalog.

## 6. Documents

- `AGENTS.md`: the Persistence row of "Where the code lives" says rows are read by column name (block 50).
- `thread_read_connections.py`'s docstrings and `sqlite_source_reader.py`'s `sqlite3.Row` annotations: block 50.

## 7. Limits and scope

### Accepted limits

- **A column written in the wrong order, or a SELECT aliasing a column under another's name, is still caught only by a
  test that gives both columns distinct values.** Today's tests do, but one: `duration_seconds` and `bitrate_kbps`
  swapped by alias in `_SQL_LIST_FILES_BASE` pass (734 passed, `rows-by-name-spec-review`). The new entry below
  carries it.

### Backlog

The closing block, as agreed by the operator on 2026-10-29:

- deletes "Rows read by column name" under "Debt";
- adds under "Technical improvements": "**Round-trip contracts**: a contract for each Writer/Reader pair and
  reader-only port of `persistence_sqlite` without one, seeded through the Writers with drawn values, so each port's
  promise is written once for any implementation. Appendix B of `agents/specs/2026-10-29-rows-read-by-column-name.md`.";
- moves "A generic way to write the tests' stubs and spies" from "Postponed" to "Technical improvements", unchanged.
  *It went to "Postponed" for want of a better section, before "Technical improvements" existed; nothing postpones
  it (operator, 2026-10-29).*

### Adjacent backlog items

- "Keyword-only calls": the same class of defect at a call site, not a row; it stays open.
- "Every catalog table STRICT": a schema's guarantee on a value's type, which a column name does not give; it stays
  open.
- "Mutation testing in the gate": would have found section 7's surviving swap mechanically; it stays open.
- "Contract tests for the fakes of outside systems": outside systems, not our stores; it stays open.
- "Multi network", stage 5; "Test quality", "Adopt ty", "The Grype scan back on p2pwatch", "Sort the files view by
  first seen", "The webui in the visitor's time zone": unrelated; they stay open.

## Appendix A. Facts

From the surveys `rows-by-name-inventory`, `rows-by-name-estimates` and the review `rows-by-name-spec-review`
(2026-10-29); the teammate re-reads them on its block's tree. Paths under `packages/crawler/`.

- **Connections.** `SqliteDatabaseOpener._connect` sets no row factory; `open_reader`
  (`thread_read_connections.py`) sets `sqlite3.Row`; `SqlitePreMigrationCopier` opens a raw candidate connection
  (line 80) and digests it. `Connection.iterdump` resets its cursor's factory (CPython 3.13 `dump.py`).
  `crawler_composition.py` gives local.db's connection to the `NodeId`, `PolicyFingerprint`, `BackoffState` and
  `TrackedDownload` stores, the catalog's to the `Observation`, `Decision`, `SourcePoint` stores and
  `CatalogScanReader`.
- **Positional reads in `src`**, by file: `observation_read.py` (an 11-index mapper shared by both connection kinds;
  `_SQL_LIST_FILES_BASE` orders its columns for it and aliases `file_size_bytes` to avoid a duplicate name, which
  D1's refusal will meet first), `sqlite_decision_store.py`, `sqlite_source_point_store.py` (`_latest_point(*row)`),
  `sqlite_tracked_download_store.py`, `sqlite_catalog_scan_reader.py`, `sqlite_node_id_store.py`,
  `sqlite_policy_fingerprint_store.py`, `sqlite_backoff_state_store.py` (tuple unpacking); `PRAGMA`s in
  `sqlite_database_opener.py` (93, 108, 133, 134), `sqlite_catalog_copier.py` (157, 182),
  `sqlite_pre_migration_copier.py` (54 to 56), `database_digest.py` (12).
- **Positional reads in tests**: 189 sites in 44 files, 23 of them migration tests (a probe that spied the reads
  of a dict factory, `rows-by-name-estimates`); 83 sites compare a row with a tuple or unpack it.
  `tests/support/catalog_rows.py` returns rows to its callers: block 30 traces who reads them before changing its
  return type. `test_database_digest.py` digests raw connections: D4 keeps it green.
- `migrations/local/0004_drop_verification_tasks.sql:6` holds `DownloadState(row[1])` in a comment, hence
  criterion 4's `*.py` pathspec.

## Appendix B. What this Discuss settled for the round-trip contracts

Agreed with the operator on 2026-10-29, for the lot that takes the "Round-trip contracts" entry; that lot's Discuss
reopens what it needs.

- **A contract per Writer/Reader pair, even with one implementation**: `Observation`, `Decision`, `SourcePoint`. A
  contract states, test first, what any implementation must do; an adapter's test covers the branches of that one
  implementation. Revises D2 of `agents/specs/2026-10-25-fake-contract-tests.md`.
- **A contract per reader-only port** (`CatalogFileReader`, `CatalogScanReader`, `CoverageReader`,
  `NodeStateReader`, `SourceReader`), one abstract fixture per port it uses, seeded through the Writers only: a raw
  SQL seed holds only for SQLite (Rainsberger, contract and collaboration tests).
- **Wide values drawn, narrow ones explicit**, so no draw picks a Python branch and a module's coverage stays the
  same from run to run; a `files` row without an observation stays in its adapter's test; an adapter test a contract
  restates is deleted; the stubs of these ports are exempted by name. The seed (per test from its node id, or none)
  was left open.
- **Values a draw must avoid**: `\x1f` in a target id or rule name (`_split_concat`), a lone surrogate
  (`UnicodeEncodeError`), an integer of `2**63` or more, a non-canonical native id, and the `CHECK`s
  `attempts >= 1`, `delay_seconds >= 0`, `last_seen_at >= first_seen_at`, `received_bytes >= 0`,
  `transfer_counter >= 0`.
- **Facts the survey found**: the foreign keys to `files` make the `Decision`, `SourcePoint`, `Coverage` and
  `Source` contracts seed through `ObservationWriter`; every double of these ports is a stub or a spy; `Network` has
  one member, so a swap between two `Network` columns stays invisible until stage 5. The swap that passes on `main`
  (section 7) is the contracts' first evidence.

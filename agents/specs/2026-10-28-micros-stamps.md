# Every stamp an integer of microseconds since the epoch

Tier Spec. Discussed with the operator on 2026-10-28. Ships the `BACKLOG.md` debt entry of the same name, added by
D12 of `agents/specs/2026-10-14-monotonic-clock.md`.

How to read it: section 1 says the problem, section 2 what the operator will see, section 3 the choices and why.
Section 4 is the design, with the identifiers. Sections 5 to 7 are the tests, the blocks and the limits. Appendix A
holds the facts.

## 1. The problem

Two representations of an instant live side by side in the databases. The catalog's observations, its source
points and `local.db`'s backoff states store an integer of microseconds since the epoch, under a bare `_at` name
the glossary refuses ("`micros`: never a bare `_at` on an `int`"). The decisions, the downloads and the node's
creation still store ISO-8601 text, written by `utc_iso` and read back by `datetime.fromisoformat` (appendix A).
Three stores even convert through the text to reach the integer (`iso_to_micros(utc_iso(x))`), and
`persistence_sqlite` defines its own `_EPOCH` seven times.

## 2. What the operator will see

- **Nothing on the pages.** The webui shows the same dates: the stores convert at the boundary and the domain keeps
  its `datetime`s.
- **At the upgrade, a copy of each database**, as for any migration that rewrites rows. On the node, whose
  databases are at version 5, this adds no copy: 0006 already makes one, and one copy covers every pending
  migration. A node already at catalog 13 (one running a `main` image) pays a full copy of its catalog, and needs
  the free space for it.
- **A `node_id` without its `created_at` stops the upgrade** (D7): the log reads `NOT NULL constraint failed:
  node_identity.created_at_micros`, the migrations before local 0015 stay applied, and the crawler does not
  start; going back to v4 means restoring `local.db`'s copy with the lowest number. No known database is in that
  state. (Corrected: `local.db` does not stay as it was, since each migration commits on its own; the holistic
  review, fixed in block 60.)
- **In the SQL console, every stamp is an integer named `<x>_micros`**: `observed_at_micros`, `decided_at_micros`,
  `queued_at_micros` and the others; `node_runtime` is gone, its two values in `node_identity`.
  `docs/migration-4x.md` lists the change beside the other renamed columns.

## 3. Decisions

Each decision is the choice, then its reason.

- **D1. Every stamp is an integer of microseconds, its column named `<x>_micros`.** The text ones are converted
  and renamed: `match_decisions.decided_at_micros`; `downloads.queued_at_micros`, `completed_at_micros`,
  `latest_seen_at_micros`, `latest_progress_at_micros`; `node_identity.created_at_micros`. The integer ones are
  renamed: `observations.observed_at_micros`, `source_observations.observed_at_micros`,
  `backoff_states.started_at_micros`. *The glossary's `micros` row and "a quantity carries its unit unless its type
  does": an SQLite `INTEGER` carries none, and the console, which has no reference page, shows the unit in the name
  (operator, 2026-10-28). The domain keeps its `datetime` fields under their `_at` names.*
- **D2. `local.db` becomes `STRICT` throughout, the catalog not yet.** `downloads`, `node_identity` and
  `reevaluation_state` are rebuilt `STRICT`, beside `backoff_states`; `match_decisions` is rebuilt as it is.
  *All or nothing per database (operator, 2026-10-28): `local.db`'s tables hold a few dozen rows, while the catalog's
  would mean rebuilding its largest tables. A new `BACKLOG.md` entry carries the catalog (section 7).*
- **D3. `node_runtime` becomes `node_identity`**, a typed one-row table, `CHECK (id = 1)` as `reevaluation_state`.
  *A key/value table of `TEXT` would turn the integer back into text (operator, 2026-10-28); one row also makes
  "both values or neither" a single insert.*
- **D4. One conversion pair, `instant_to_micros(instant)` and `micros_to_instant(micros)`**, in
  `persistence_sqlite/micros.py`, beside `iso_to_micros`, which moves there from `variants.py`. `micros.py` replaces
  `connection.py`, deleted with `utc_iso`. A naive `datetime` raises `ValueError`, as `utc_iso` did. *Names on the
  model of `iso_to_micros`, saying what goes in and what comes out (operator, 2026-10-28); one module ends the
  copies of `_EPOCH` and of `_micros`.*
  *Amended in block 60 (operator, 2026-10-28): `iso_to_micros` is deprecated, for the migrations only. Python
  marks it `@warnings.deprecated(..., category=None)`, no runtime warning, and mypy's `deprecated` error code
  refuses every reference but its registration in `variants.py`; the opener removes the SQL function once the
  migrations are applied, so a store's SQL calling it fails at once. A text stamp is only ever an older
  database's, read while migrating. (Corrected: D4 kept `iso_to_micros` as an ordinary conversion beside the
  pair.)*
- **D5. The three migrations that rebuild a table carry `-- migration: copy-before`; the two that only rename do
  not.** *A rebuild is an `INSERT ... SELECT` and a `DROP TABLE`, which `test_migration_directives.py` requires
  marked; a `RENAME COLUMN` rewrites the schema and no row, as catalog 0012 says.*
- **D6. `match_decisions` keeps every row's `id`.** *The reads break a tie on the decision's instant with
  `id DESC`.*
- **D7. A `node_id` without its `created_at` fails the migration** instead of dropping the identity, on
  `node_identity`'s `NOT NULL`. *A node that loses its id writes under a new one from then on; a failed migration
  rolls back, and the copy is there. The constraint names the table and the column, where a failure inside
  `iso_to_micros` would name neither.*
- **D8. The databases' schema gets no reference page for console users.** *The console is an unstable surface, for
  power users and tinkerers only (operator, 2026-10-28). `docs/migration-4x.md` still lists the schema change, as it
  lists every renamed column.*
- **D9. A block per change of the schema**: both renames in one block (catalog 0014, local 0013), then the
  decisions (catalog 0015), the downloads (local 0014), `node_identity` and `reevaluation_state` (local 0015).
  *Each block ships its migrations with the stores that read them, so the gate stays green; the renames are
  mechanical and take the exemption past 20 files rather than a split by database (operator, 2026-10-28). The node
  still pays one copy per database, which covers every pending migration.*

## 4. Design

### 4.1 `micros.py`

- `instant_to_micros(instant: datetime) -> int`: the microseconds since the epoch of an aware instant; a naive one
  raises `ValueError`.
- `micros_to_instant(micros: int) -> datetime`: the aware UTC instant.
- `iso_to_micros(stamp: str) -> int`: `instant_to_micros(datetime.fromisoformat(stamp))`, which
  `register_sql_functions` keeps registering for the migrations (catalog 0007 and three of this lot).

Every conversion of `persistence_sqlite` goes through them: the stores' `iso_to_micros(utc_iso(x))`, the
readers' `_EPOCH + row * _MICROSECOND` and `_EPOCH + timedelta(microseconds=...)`, the private `_micros`. A
`timedelta` converted to microseconds (`window.gap // _MICROSECOND`) is no instant and stays. The webui's
`format.py` keeps its own `_EPOCH`: an adapter never imports another.

### 4.2 The scripts

Each rebuild follows the recipe of `docs/contributing/architecture.md` ("Remplacer une table"): drop the old
table's triggers and indexes, rename it, create the new one under the final name, copy, drop the old one, create
the triggers again. A stamp that may be `NULL` is converted by `CASE WHEN x IS NULL THEN NULL ELSE
iso_to_micros(x) END`: `iso_to_micros` receiving `NULL` fails the whole script.

- **Catalog 0014, `0014_micros_names.sql`**: `RENAME COLUMN observed_at TO observed_at_micros` in `observations`
  and in `source_observations`.
- **Local 0013, `0013_micros_names.sql`**: `RENAME COLUMN started_at TO started_at_micros` in `backoff_states`.
- **Catalog 0015, `0015_decision_micros.sql`**: `match_decisions` with `decided_at_micros INTEGER NOT NULL` in
  place of `decided_at`, every row's `id` and other columns copied; then the index on `(file_id, target_id,
  decided_at_micros)` and the triggers `match_decisions_no_update` and `match_decisions_no_delete`, as
  `catalog/0008_file_id.sql` wrote them. The index is renamed `idx_match_decisions_file_target_decided_at_micros`,
  after its columns.
- **Local 0014, `0014_download_micros.sql`**: `downloads` rebuilt `STRICT`, its four stamps `INTEGER` under their
  `_micros` names, `queued_at_micros NOT NULL`, the other three nullable; every other column, `UNIQUE` and `CHECK`
  as today.
- **Local 0015, `0015_node_identity.sql`**:
    - `node_identity (id INTEGER PRIMARY KEY CHECK (id = 1), node_id TEXT NOT NULL, created_at_micros INTEGER NOT
      NULL) STRICT`, filled from `node_runtime`'s `node_id` row, `LEFT JOIN`ed to its `created_at` row and converted
      with the `CASE`, so a missing `created_at` reaches the `NOT NULL` (D7). `node_runtime` is dropped, with any
      other key: no code reads one.
    - `reevaluation_state` rebuilt `STRICT`, the same columns and row.

### 4.3 The stores

- **Block 20.** Every SQL that names `observed_at` names `observed_at_micros`: the observation and source point
  stores, `observation_read.py`, the source reader, the catalog file reader, the catalog copier, and the tests' raw
  SQL and seeds. The same for `started_at`: the backoff store and the node state reader, and their tests. A test
  that only reads the domain's `observed_at` or `started_at` field is unchanged.
- **Block 30.** `SqliteDecisionStore` writes `instant_to_micros`, `SqliteCatalogFileReader` reads
  `micros_to_instant`. The merge's deduplication compares `decided_at_micros` on both sides, both at the current
  version. The test seeds of the decisions become integers: `tests/support/catalog_rows.py` (`SEEN_AT`, the default
  of `insert_decision`), `tests/support/adapters/driven/persistence_sqlite/catalog_seeds.py`, and the literals of
  `test_sqlite_catalog_file_reader.py`, `test_sqlite_coverage_reader.py` and `test_sqlite_catalog_copier.py`. The
  catalog is not `STRICT`, so a text seed left behind would pass silently.
- **Block 40.** `SqliteTrackedDownloadStore` writes and reads through the pair, `SqliteNodeStateReader` reads the
  downloads through `micros_to_instant`. The compose smoke's seed (`tests/integration/test_compose_smoke.py`) writes
  integers: `STRICT` refuses its text.
- **Block 50.** `SqliteNodeIdStore` and `SqliteNodeStateReader` read and write `node_identity`;
  `record_node_id` becomes one `INSERT`, without its explicit transaction (the connections are in autocommit).
  `connection.py` and `test_connection.py` are deleted. The webui's four docstrings that describe an instant "as
  `utc_iso` writes it" or "as local.db stores it" (`webui/app.py:223,603`, `webui/displays.py:80,95`) say what they
  hold instead.

### 4.4 Documents

- `docs/contributing/architecture.md`: the schema diagrams (`node_identity`, the `_micros` names), the versions
  (catalog 15, local 15), the five migrations in the history paragraph. Each block for its migration.
- `docs/migration-4x.md`: a passage on the stamps as `_micros` integers and `node_runtime` as `node_identity`,
  beside the two schema bullets, which name none of these columns today. Each block for its change.
- `AGENTS.md`: the glossary's `micros` row says the rule holds for a column as for a Python name (block 20).

## 5. Acceptance

Criteria 1 to 9 are tests, each watched failing before its implementation; criterion 10 is evidence.

1. `instant_to_micros` and `micros_to_instant` are inverse on an instant with microseconds; a naive instant raises
   `ValueError`; `iso_to_micros` reads a stamp with and without a fraction and with a non-UTC offset.
2. A catalog at version 13 with observations and source points migrates to 14, and a `local.db` at version 12
   with a backoff state to 13: each row reads back unchanged under the `_micros` name, and no
   column named `observed_at` or `started_at` is left.
3. A catalog at version 14, holding decisions whose stamps have and lack a fraction, migrates to 15: each row keeps
   its `id` and every column, `decided_at_micros` the micros of its text.
4. After catalog 0015, `user_version` is 15; an `UPDATE` and a `DELETE` on `match_decisions` raise
   `match_decisions is append-only`; `pragma_index_info` of its index lists `file_id`, `target_id`,
   `decided_at_micros`.
5. A `local.db` at version 13 migrates to 14: each download's stamps are its texts' micros, a `NULL` stays `NULL`.
6. A `local.db` at version 14 migrates to 15: `node_identity` holds the node id and the micros of its `created_at`;
   `reevaluation_state` keeps its row; `node_runtime` is gone; `SELECT name FROM pragma_table_list WHERE schema =
   'main' AND type = 'table' AND NOT strict AND name NOT LIKE 'sqlite_%'` returns no row.
7. A `local.db` at version 14 holding a `node_id` without `created_at` fails to migrate with `NOT NULL constraint
   failed: node_identity.created_at_micros`, stays at version 14, and keeps `node_runtime`'s rows.
8. After each writer's call, `SELECT typeof(<column>), <column>` returns `integer` and `instant_to_micros` of the
   instant written: `SqliteDecisionStore.record_decision` for `decided_at_micros`; `SqliteTrackedDownloadStore`'s
   calls for the four download stamps; `SqliteNodeIdStore.record_node_id` for `created_at_micros`.
9. Each instant written reads back to the microsecond through its reader: `SqliteDecisionStore` then
   `SqliteCatalogFileReader`; `SqliteTrackedDownloadStore` and `SqliteNodeIdStore` then `SqliteNodeStateReader`.
10. At the top of the stack, `git grep -n "utc_iso\|fromisoformat" packages/crawler/src` prints `micros.py`'s line
    in `iso_to_micros` and the webui's own parsing of a URL's instant (`webui/format.py`), nothing else; and
    `git grep -n "^_EPOCH" packages/crawler/src/p2pwatch/adapters/driven/persistence_sqlite` prints one line, in
    `micros.py`. It fails while a copy is left.

## 6. Blocks

Estimates by `micros-estimates` (Sonnet, 2026-10-28), from the files each row touches.

| # | Branch | Holds | Lines, files |
|---|---|---|---|
| 10 | `refactor/micros-conversions` | 4.1, criterion 1; `connection.py` stays for the stamps still in text | 260, 14 |
| 20 | `refactor/micros-column-names` | catalog 0014, local 0013, 4.3's block 20, criterion 2, 4.4 | 320, 22 to 24 |
| 30 | `feat/decision-stamps-micros` | catalog 0015, 4.3's block 30, criteria 3, 4, 8 and 9 for the decisions, 4.4 | 340, 15 |
| 40 | `feat/download-stamps-micros` | local 0014, 4.3's block 40, criteria 5, 8 and 9 for the downloads, 4.4 | 330, 12 |
| 50 | `feat/node-identity-strict` | local 0015, 4.3's block 50, criteria 6 to 9 for the node, 4.4; drafts the handoff | 390, 14 |
| 60 | `docs/micros-stamps-wrap` | the closing block: the holistic findings, `BACKLOG.md`, the handoff | |

- **Block 20 passes 20 files** under the mechanical exemption: columns renamed, nothing else (operator,
  2026-10-28).

The order: the conversions first, so each later block changes its stores once; the renames of the integer stamps
before the conversions, so each conversion writes its final name once; the catalog before `local.db`; `utc_iso`
deleted once nothing writes text.

## 7. Limits and scope

### Accepted limits

- **The catalog's tables are not `STRICT`** (D2): a new `BACKLOG.md` entry, under "Technical improvements":
  "**Every catalog table STRICT**, as `local.db`'s are: all of them rebuilt at once, so SQLite refuses a value of the
  wrong type; it costs a rebuild of the catalog's largest tables. D2 of `agents/specs/2026-10-28-micros-stamps.md`."
- **A stamp `fromisoformat` cannot read, or a naive one, fails its migration**, rolled back with its copy kept. On
  the node, every stamp parses as an aware UTC instant (appendix A).

### Adjacent backlog items

- "Every stamp an integer of microseconds since the epoch": shipped, deleted by the closing block.
- "Sort the files view by first seen", "The webui in the visitor's time zone": they read instants the domain already
  holds as `datetime`; this lot changes neither.

## Appendix A. Facts

On the tree at `cb823348`, and read-only on the node's databases (2026-10-28):

- The current schemas, printed by `open_catalog` and `open_local` from the test support: catalog version 13, local
  version 12; text stamps in `match_decisions.decided_at`, `downloads`' four stamps and `node_runtime`'s
  `created_at`; integers in `observations.observed_at`, `source_observations.observed_at` and
  `backoff_states.started_at`; `backoff_states` alone `STRICT`.
- The node (v4, both databases at version 5): 16,477 decisions, 25 downloads, 20 of them with `completed_at`
  `NULL`; `node_runtime` holds `node_id` and `created_at` and nothing else. Its 16,533 non-`NULL` stamps all parse
  as aware instants at offset zero (`micros-spec-review`).
- `git grep -n "^_EPOCH" packages/crawler/src/p2pwatch/adapters/driven/persistence_sqlite`: seven definitions.
- SQLite 3.46.1 in the core image, 3.49.1 in development: both have `pragma_table_list`'s `strict` column. A
  `DROP TABLE` fires no `BEFORE DELETE` trigger; `STRICT` refuses ISO text in an `INTEGER` column
  (`micros-spec-review`'s spike).

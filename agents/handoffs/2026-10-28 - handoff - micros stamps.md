# Handoff: every stamp an integer of microseconds since the epoch

Drafted by block 50 from the lot's block reports (#525, #526, #528, #529, #530) and its own, for the closing block 60
to correct with the holistic review.

## State

Tier Spec lot. Spec `agents/specs/2026-10-28-micros-stamps.md` (reviewed by `micros-spec-review`, approved by the
operator 2026-10-28). It ships the backlog entry "Every stamp an integer of microseconds since the epoch" (D12 of
`agents/specs/2026-10-14-monotonic-clock.md`), which the closing block deletes from `BACKLOG.md`, and adds the entry
"Every catalog table STRICT" (spec 7, D2).

One stack cut from `main` at `cb823348`, which had not moved when block 50 was drafted (`git fetch`, 2026-10-28).
Seven blocks: block 25 was cut under block 30 by the lead, since block 30 reached 22 files against its parent.
Block 20 took the mechanical exemption on its spec row (30 files).

| Block | Pull request | Branch |
|---|---|---|
| 10 | #525 | `refactor/micros-conversions` |
| 20 | #526 | `refactor/micros-column-names` |
| 25 | #528 | `test/older-catalog-decisions` |
| 30 | #529 | `feat/decision-stamps-micros` |
| 40 | #530 | `feat/download-stamps-micros` |
| 50 | #TBD | `feat/node-identity-strict` |
| 60 | | `docs/micros-stamps-wrap` |

Not merged at writing. **No release follows this lot**: the v5 waits for a P2P network other than eD2k (operator,
2026-10-27). The lot changes what the image ships (five migrations, the stores), so it reaches the node only with the
v5 release, or through a `main` image the operator chooses to run.

## What was built

- **The conversions** (block 10, D4): `persistence_sqlite/micros.py` holds `instant_to_micros`, `micros_to_instant`
  and `iso_to_micros` (moved from `variants.py`), the one `_EPOCH` of `persistence_sqlite`. `instant_to_micros` and
  `iso_to_micros` raise `ValueError` on a naive instant. Every store's `iso_to_micros(utc_iso(x))`, every reader's
  `_EPOCH + ...` and the private `_micros` go through them. `sqlite_source_reader.py` keeps `_MICROSECOND` for
  `window.gap // _MICROSECOND`, a `timedelta`, not an instant.
- **The renames** (block 20, D1): catalog 0014 renames `observed_at` to `observed_at_micros` in `observations` and
  `source_observations`, local 0013 `backoff_states.started_at` to `started_at_micros`, both by `RENAME COLUMN`,
  unmarked (D5). Every SQL that named them, in the stores and the tests, follows. `AGENTS.md`'s glossary row for
  `micros` holds for a column as for a Python name.
- **The decisions' seeds** (block 25): `older_catalog.py`'s `insert_v14_decision` seeds older catalogs' decisions,
  with the `decision_id` that block 30's migration test checks.
- **The decisions** (block 30): catalog 0015 rebuilds `match_decisions` with `decided_at_micros INTEGER NOT NULL`,
  every row's `id` kept (D6), its index renamed `idx_match_decisions_file_target_decided_at_micros` and its two
  append-only triggers recreated; marked `copy-before`. `SqliteDecisionStore` writes `instant_to_micros`,
  `SqliteCatalogFileReader` reads `micros_to_instant`, the merge compares `decided_at_micros` on both sides.
- **The downloads** (block 40): local 0014 rebuilds `downloads` `STRICT`, its four stamps `INTEGER` under their
  `_micros` names, `queued_at_micros NOT NULL` alone; marked `copy-before`. `SqliteTrackedDownloadStore` writes and
  reads through the pair, `SqliteNodeStateReader` reads them through `micros_to_instant`. The compose smoke's seed
  writes integers.
- **The node identity** (block 50, D3, D7): local 0015 replaces `node_runtime`'s key/value rows with
  `node_identity (id CHECK (id = 1), node_id TEXT NOT NULL, created_at_micros INTEGER NOT NULL) STRICT`, filled from
  the `node_id` row `LEFT JOIN`ed to the `created_at` row, so a missing `created_at` fails the migration on the
  `NOT NULL`; any other key of `node_runtime` is dropped with it. `reevaluation_state` is rebuilt `STRICT`, so every
  table of `local.db` is. Marked `copy-before`. `SqliteNodeIdStore.record_node_id` is one `INSERT` of row 1, without
  its explicit transaction (the connection is in autocommit; a second id hits the primary key, `StoreError` as the
  port promises). `connection.py`, `utc_iso` and `test_connection.py` are deleted. The webui's four docstrings that
  described an instant as `utc_iso` or `local.db` stored it say "ISO-8601 to the microsecond".
- **The documents**: `docs/contributing/architecture.md` (the diagram's `node_identity`, catalog 15, local 15, the
  five migrations in the history paragraph) and `docs/migration-4x.md` (the `_micros` columns, `node_runtime` as
  `node_identity` and the refusal of a `node_id` without `created_at`), each block for its migration. Block 20 also
  corrected `architecture.md`'s versions, one behind each before the lot.

## Evidence

Every block's `uv run poe check` exit 0 at its tip (crawler: 1687 passed at block 10, 1698 at block 50; 100 % branch
coverage; `_unit-coverage-check` clean). `uv run poe docs-build` "No issues found" at blocks 20, 30, 40 and 50.

Budgets against each parent: block 10, 194 lines and 17 files; block 20, 305 and 30 (exemption); block 25, 27 and 5;
block 30, 215 and 17; block 40, 297 and 12; block 50, 255 and 14.

Criterion 10, at block 50's tip: `git grep -n "utc_iso\|fromisoformat" packages/crawler/src` prints `micros.py:23`
(`iso_to_micros`) and `webui/format.py:93`, nothing else; `git grep -n "^_EPOCH"
packages/crawler/src/p2pwatch/adapters/driven/persistence_sqlite` prints `micros.py:5` alone (since block 10).

Each criterion's test watched failing, from the block reports:

- 1 (block 10): `ModuleNotFoundError: No module named '...persistence_sqlite.micros'`, then, without the guard,
  `TypeError: can't subtract offset-naive and offset-aware datetimes`.
- 2 (block 20): `assert 13 == 14` and `assert 12 == 13` on `user_version`, and `ValueError: not enough values to
  unpack (expected 1, got 0)` for the missing script.
- 3, 4 (block 30): `sqlite3.OperationalError: no such column: decided_at_micros` and `assert 14 == 15`.
- 5 (block 40): `assert 13 == 14` and `assert (0,) == (1,)` (not `STRICT`).
- 6, 7 (block 50): `assert 14 == 15`; the `NOT strict` query listing `reevaluation_state` and `node_runtime`; `Failed:
  DID NOT RAISE MigrationError` for the `node_id` without `created_at`.
- 8: the decisions, `no such column: decided_at_micros` (block 30); the downloads, `no such column:
  queued_at_micros` and the like, 12 tests (block 40); the node, `PersistenceError: no such table: node_runtime`
  (block 50, the store run on 0015's schema).
- 9: the decisions and the downloads passed with the text already, so each was watched failing at the intermediate
  step, the store writing integers and the reader still parsing text: `TypeError: fromisoformat: argument must be
  str` (blocks 30, 40). The node's (block 50) failed only on `no such table: node_runtime`, the reader still on the
  old table; it would have passed with the text too, which kept its microseconds.

## Departures from the spec

- Block 10: `iso_to_micros` on a naive stamp raises `ValueError`, where it raised `TypeError`; its tests moved to
  `test_micros.py`. The test-local conversions of `test_sqlite_source_point_store.py` and
  `test_sqlite_source_reader.py` stay, as independent oracles of the stores' integers.
- Block 25: the block itself, which section 6 does not have.
- Block 30: `insert_decision` (`tests/support/catalog_rows.py`) keeps a `decided_at: str` and writes
  `iso_to_micros` of it, as `insert_observation` does, so the seeds' ISO literals stay readable; only the copier
  test's `"t1"` seed became `_T1`.
- Block 40: `SqliteNodeStateReader`'s `created_at` read `datetime.fromisoformat` inline until block 50.
- Block 50: `test_a_failed_record_is_rolled_back_whole` is removed (one `INSERT` cannot half-write, and the
  contract's `test_a_second_node_id_is_refused` covers the conflict); `test_a_naive_created_at_does_not_wedge_the_connection`
  becomes `test_a_naive_created_at_raises_and_records_nothing`, since no transaction is left to wedge.

## Class 1 fixes

- Block 20: `test_migration_0013.py` and `test_local_migration_0012.py` pinned to their own version
  (`open_*_at(path, N)`); two integer parameters renamed `_micros`; `architecture.md`'s versions corrected.
- Block 50: the webui's private `_stored_instant` renamed `_iso_instant`, its name no longer true once `local.db`
  stores no text.

No class 2 question in the lot.

## The holistic review

For the closing block: findings and their exits.

## Counts

For the closing block: fix-backs, cascaded rebases and the runs they re-triggered. At block 50's drafting: none.

## Pitfalls

- A migration test that opens through `open_catalog`/`open_local` breaks at every later migration: pin it with
  `open_*_at(path, N)` (block 20).
- A column inside an SQL string is no symbol: the renames went by a word-bounded regex on the SQL aliases, then
  `git grep`, leaving the domain's `.observed_at` and `.started_at` alone (block 20).
- `test_sqlite_catalog_copier.py`'s `_CURRENT_SCHEMA_VERSION` and `test_sqlite_database_opener.py`'s version asserts
  move with every migration; so does `test_local_migration_0007.py`'s seed, with the `downloads` columns.
- The catalog is not `STRICT`: a text seed left behind in a decision passes silently (block 30). `local.db` now
  refuses one.
- `docs/troubleshooting.md` and `architecture.md` section 7 name `latest_seen_at` as the domain's field, not the
  column, and stay.
- A new migration test file needs its line in the crawler's `[tool.coverage_checks] tests_without_unit`.

## Not validated

- **The node's upgrade under this code**: its databases at version 5 go to catalog 15 and local 15 under one copy
  each (0006 already makes one); not run. A node at catalog 13 (a `main` image) pays a full copy of its catalog.
- The integration suites, the compose smoke's integer seed included, run only in CI's `validate / gate`.

## Next

No release proposal: the v5 waits for a P2P network other than eD2k. Then `BACKLOG.md`, read before proposing.

# Every catalog table STRICT

Tier Spec. Discussed with the operator on 2026-11-01, from `BACKLOG.md`'s "Every catalog table STRICT".

## 1. In short

The catalog's tables declare their column types but do not enforce them: SQLite stores a text in an `INTEGER` column,
and nothing bounds a size, a tier or an instant. The node's own writes are checked by the domain, but `merge` copies
another node's rows, and the lot "Values checked at the boundary" left these values to this lot (its D9).

The lot makes every catalog table `STRICT`, with sign, closed-set and instant `CHECK`s, in the `CREATE TABLE`s v5's
unreleased migrations already write, so no table is rebuilt for it. `merge` then refuses through the destination's
schema a source holding such a value: no check is added to `merge` itself.

## 2. What the operator will see

- `merge` refuses a source holding, in a column it copies, a value of the wrong type, a negative quantity, an unknown
  tier or an instant out of range, the source whole, at copy time (D3).
- In the SQL console, `PRAGMA table_list` shows every catalog table `strict`; every read is unchanged.
- The upgrade to v5 rebuilds nothing more, and none of the operator's v4 rows is refused (Appendix B).

## 3. Decisions

- **D1. Every catalog table is `STRICT`, declared where v5's migrations create it: `files`, `observation_variants`
  and `observations` in 0008, `sources` in 0010, `source_variants` and `source_observations` in 0011,
  `match_decisions` in 0015.** *No release holds a migration past 0005, and no catalog to keep has passed 0007
  (operator, handoff of the lot "One domain type for arbitrary JSON"), so operators pay no rebuild for it; 0008
  already rebuilds the v4 tables, and every v4 row the operator holds passes (Appendix B).* 0010's `source_variants`
  and `source_ranges` stay as they are: 0011 drops both.
- **D2. Each column the node reads as a quantity, a closed set or an instant gets its `CHECK`**: `>= 0` on both
  `size_bytes`, `duration_seconds`, `bitrate_kbps` and `source_count`; `tier IN ('catalog', 'notify', 'download',
  'retracted')`; `connectable IN (0, 1)`; each `*_micros` between the micros of `datetime.min` and `datetime.max` in
  UTC. *Each bound is the one the node already relies on: `is_quantity` (with `STRICT`'s 64-bit `INTEGER`), the
  tiers and the retraction the decision reader knows, and `micros_to_instant`, which raises `OverflowError` outside
  that range. These are what D9 of `agents/specs/2026-10-30-values-checked-at-the-boundary.md` left to this lot.* The
  existing `CHECK`s (network, `native_id`, role, `session_received_bytes`) stay.
- **D3. `merge` checks nothing more: the destination's schema refuses such a value in a column the copy writes (every
  column but the observations' `variant_id`, which the copy joins on and replaces) at copy time, the source whole,
  the sources the same command copied before it staying merged (D11 of the lot "Values checked at the boundary").**
  *A source a v5 node wrote cannot hold such a value, since its own tables are `STRICT` with the same `CHECK`s; only a
  source whose schema is not the node's can, which the new backlog entry covers (section 7). A check before the copy
  could not hold the `CHECK`s anyway: `quick_check` skips them on a source attached `mode=ro`, as `merge` attaches
  every source (Appendix C), and restating them in code would copy the schema.* (Operator, 2026-11-01, after weighing
  `quick_check` and a `typeof` query before the copy.)

The operator decided D1 to D3 on 2026-11-01.

## 4. Acceptance

1. A catalog the opener creates has every table of `main` but SQLite's own `STRICT` (`pragma_table_list`).
2. Each `CHECK` of D2 refuses its value at insert: -1 in each sign column, an unknown tier, `connectable = 2`, each
   `*_micros` one past each bound; and accepts 0, each bound and `NULL` where the column allows it.
3. A v4 catalog holding a row in each v4 table, at Appendix B's extremes and with a `retracted` row whose `target_id`
   is `''`, migrates to the current version, every table `STRICT`, its `PRAGMA quick_check` `ok` on a read-write
   connection.
4. `merge`, in both its modes, given a clean source then a source holding one of: a non-numeric text in an `INTEGER`
   column of a rowid table (`files.size_bytes`) and of a `WITHOUT ROWID` one (`observations.source_count`), each
   `CHECK` of D2 broken, refuses the second source whole, names it, and keeps the first merged. On `main`, each of
   these merges.
5. `uv run poe check` passes at each block's tip.

## 5. Blocks

One block and the closing one: `merge` keeps working at block 10's tip, its destination refusing what its schema
refuses. Estimates by `strict-catalog-estimates` (Sonnet), 2026-11-01; the bound is checked after committing.

| # | Branch | Holds | Lines, files |
|---|---|---|---|
| 10 | `feat/strict-catalog-schema` | D1, D2, D3 | 400 (360 to 450), 14 |
| 20 | `docs/wrap-strict-catalog` | closing, section 6's operator documents | 35, 3 |

Block 10 is the tightest: acceptance 4's cases are parametrized over one forging helper, not written one test each.

## 6. Documents

- `docs/migration-4x.md`: the catalog's tables `STRICT` and their `CHECK`s, as it lists every schema change (block
  20).
- `docs/operate.md`, the catalog merge: the values it refuses (block 20).
- The closing block's handoff.

## 7. Limits and scope

### Accepted limits

- **A source whose column declarations were altered can hold a value the destination converts without loss** (a text
  `'123'` stored as `123`): only a hand-edited source can (Appendix C), and the new backlog entry refuses it.
- **A catalog a pre-lot v5 build migrated keeps its tables as they were**, and `merge --into` it refuses none of
  section 2's values: no catalog to keep has passed 0007 (operator).
- **An observation or a source observation whose `variant_id` names no variant of its source is skipped, as on
  `main`**: the node writes with `foreign_keys=ON`, so only a source written outside it, on purpose, holds one, and
  a merge is between peers one trusts (D10 of the lot "Values checked at the boundary"). (Operator, 2026-11-01, after
  the spec review: an adversarial case, improbable, unlike the different schema a fork or a dev database can carry.)
- **`local.db` gets no `CHECK`**: `merge` never reads it, and only the node's own checked values reach it.

### Backlog

With block 10's first commit, as agreed on 2026-11-01: "`merge` refuses a source whose schema is not the node's"
added under "Technical improvements": a catalog at the current version whose declarations differ (a fork's, a dev
database, a pre-lot build's) would be refused before any copy; such a check must accept the `sqlite_stat*` tables a
researcher's `ANALYZE` adds (the spec review). The closing block deletes "Every catalog table STRICT".

### Adjacent backlog items

- "`merge` refuses a source whose schema is not the node's": added by this lot, out of its scope (operator); it stays
  open.
- "Round-trip contracts": the next lot; its contracts seed through the Writers, whose values the schema now bounds too;
  it stays open.
- "aMule 3.2.0 pinned", "The Grype scan back on p2pwatch": with the round-trip contracts, the other conditions of the
  v5 tag; they stay open.
- The other items are unrelated and stay open.

## Appendix A. Design

Paths under `packages/crawler/src/p2pwatch/adapters/driven/persistence_sqlite/`.

- **The migrations**: `) STRICT;` or `) STRICT, WITHOUT ROWID;` closes each `CREATE TABLE` D1 names, and each D2
  `CHECK` is written under the column's name at that migration (`directly_reachable` in 0011, `observed_at` in 0008
  and 0011): `ALTER TABLE ... RENAME COLUMN` (0012, 0014) rewrites a `CHECK` with its column (the review's probe, on
  SQLite 3.46.1, 3.49.1 and 3.54.0). The two instant bounds are literals, -62135596800000000 and
  253402300799999999, with a one-line comment naming `datetime.min` and `datetime.max`. The rebuilds of 0008 and 0015
  copy into the `STRICT` tables as they do today.
- **The tests**: no existing test writes a value `STRICT` refuses (`strict-catalog-estimates` ran the crawler's suite
  over the patched migrations outside the repository; the review counted 1981 passed at a8f0f777). A merge test
  forges a wrong type by recreating a source table without `STRICT`, under the same columns, then inserting the row
  (the append-only triggers refuse an `UPDATE`), the text non-numeric (`'abc'`: affinity stores `'123'` as `123`); a
  broken `CHECK` under `PRAGMA ignore_check_constraints`, as the copier tests do today. A forged variant carries
  `content_hash` or `source_content_hash` over its forged values, or the existing check pass refuses it before any
  copy. The existing `_ROWS_THE_SCHEMA_REFUSES` cases keep passing.

## Appendix B. Facts, 2026-11-01

The operator's catalog, `/home/geoffrey/Projets/mulewatch/data/catalog.db`, `user_version` 5, the node stopped (D7 of
the lot "Values checked at the boundary").

- 0006 drops v4's source tables, so only `files`, `file_observations` and `match_decisions` carry rows into v5.
- `files`: 2 162 rows, `ed2k_hash` text, `size_bytes` integer from 196 to 28 737 952 534.
- `file_observations`: 15 763 676 rows, each column of its declared type or `NULL`; no negative size, count, duration
  or bitrate; `source_count` 0 to 12, `media_length_sec` 32 to 3 576, `bitrate_kbps` 0 to 4 498; `observed_at` from
  `2026-07-04T04:30:19.228441+00:00` to `2026-10-28T21:43:14.401885+00:00`.
- `match_decisions`: 16 477 rows, every column text; tiers `catalog` 775, `download` 8 342, `notify` 3 053,
  `retracted` 4 307, of which 7 with `target_id = ''` (the old retraction model); `decided_at` from 2026-07-04 to
  2026-10-25.

Queries: `SELECT typeof(<column>) ..., COUNT(*) ... GROUP BY ...` per table, `SUM(<column> < 0)`, `MIN`, `MAX`, and
`SELECT tier, target_id = '', COUNT(*) FROM match_decisions GROUP BY 1, 2`.

## Appendix C. Probes, 2026-11-01

On SQLite 3.49.1 (the host's) and 3.46.1 (`ghcr.io/mission-titar/p2pwatch:main`'s), the same results. Each probe
printed the `typeof` of the value it forged, and turned `ignore_check_constraints` back off before reading.

- **Copy into a `STRICT` destination**, `INSERT ... SELECT ... WHERE true ON CONFLICT DO NOTHING` from a source attached
  `mode=ro` whose tables carry no `STRICT`, `NOT NULL` nor `CHECK`, in a transaction: a text in an `INTEGER` column
  (rowid and `WITHOUT ROWID`), a `NULL` in a `NOT NULL` column and a broken `CHECK` (rowid and `WITHOUT ROWID`) each
  raise `IntegrityError` and leave no row once rolled back.
- **Affinity**: a text `'123'` written to an `INTEGER` column, `STRICT` or not, is stored as the integer `123`; an
  integer written to a `TEXT` column, `STRICT` or not, as the text `'4'`, which Python reads as a `str`. A value its
  column's affinity would convert without loss (`'123'`, `2.0`, `4` into `TEXT`) exists only where the declaration
  was rewritten after the write; a table without `STRICT` keeps one affinity cannot convert (`'abc'`, `1.5` in
  `INTEGER`, a blob in `TEXT`; the spec review).
- **`PRAGMA quick_check`** refuses a value of the wrong storage class and a `NULL` in a `NOT NULL` column on a source
  attached `mode=ro`, but no `CHECK`; on a read-write connection it refuses a broken `CHECK` too, rowid and `WITHOUT
  ROWID`. It honours `ignore_check_constraints`.

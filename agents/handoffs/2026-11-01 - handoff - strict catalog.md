# Handoff: every catalog table STRICT

Drafted by block 10 from its own report, for the closing block 20 to correct with the holistic review and its own
report.

## State

Tier Spec lot. Spec `agents/specs/2026-11-01-strict-catalog.md`, D1 to D3 approved by the operator on 2026-11-01, from
`BACKLOG.md`'s "Every catalog table STRICT". Spec reviewed by `strict-catalog-spec-review`; estimates by
`strict-catalog-estimates` (Sonnet); holistic review: to come.

One stack cut from `main` at `a8f0f777`, two blocks, the closing one included.

| Block | Pull request | Branch |
|---|---|---|
| 10 | (block 10's) | `feat/strict-catalog-schema` |
| 20 | (to open) | `docs/wrap-strict-catalog` |

Not merged at writing. What the operator sees (spec section 2): `merge` refuses a source holding, in a column it
copies, a value of the wrong type, a negative quantity, an unknown tier, `connectable` other than 0 or 1, or an
instant out of `datetime`'s range, the source whole, at copy time; `PRAGMA table_list` shows every catalog table
`strict`. Nothing else: the upgrade from v4 rebuilds no more tables than before.

## What was built

- **The schema** (block 10, D1, D2): `) STRICT;` or `) STRICT, WITHOUT ROWID;` closes `files`, `observation_variants`
  and `observations` in 0008, `sources` in 0010, `source_variants` and `source_observations` in 0011, `match_decisions`
  in 0015. The `CHECK`s, under each column's name at its migration: `size_bytes >= 0` on `files` and
  `observation_variants`, `media_length_sec`, `bitrate_kbps` and `source_count >= 0`, `directly_reachable IN (0, 1)`,
  `tier IN ('catalog', 'notify', 'download', 'retracted')`, and `observed_at` (0008, 0011) and `decided_at_micros`
  (0015) `BETWEEN -62135596800000000 AND 253402300799999999`, one comment line naming `datetime.min` and
  `datetime.max`. 0012 and 0014's `RENAME COLUMN` carry the `CHECK`s to `duration_seconds`, `connectable` and both
  `observed_at_micros` (the refusal messages name them). 0010's `source_variants` and `source_ranges` are untouched,
  0011 drops both.
- **`merge`** (block 10, D3): no code change. The copier's tests forge every row through one helper, `_forge`, which
  recreates the table without `STRICT` when the forged value is of the wrong type, writes the row under
  `ignore_check_constraints`, turns it back off and checks it, and checks the row holds the value with the storage
  class it was bound with. The existing rows the schema refuses (`_ROWS_THE_SCHEMA_REFUSES`, `_BOGUS_ROLE`) go through
  it too.

## Evidence

`uv run poe check` exit 0 at block 10's tip (crawler: 2040 passed, 15 deselected). Continuous integration: see block
10's pull request.

Budget against `main` (lines, files; estimate in parentheses): 10, 365 and 8 (400, 14).

Acceptance:

- 1: `test_open_catalog_makes_every_table_strict` (`test_sqlite_database_opener.py`) failed first on `AssertionError:
  assert {'match_decis...rces': 0, ...} == {'sources': 1...ions': 1, ...}`, every table at 0.
- 2: `test_append_only.py`, 13 refused cases (-1 in each of the five sign columns, the tier `rejected`, `connectable =
  2`, each of the three `*_micros` one past each bound) failed first on `Failed: DID NOT RAISE IntegrityError`; the 23
  accepted cases (0, each tier, `connectable` 0, 1 and `NULL`, `NULL` duration and bitrate, each bound) passed on
  `main` too, as they should.
- 3: `test_a_version_5_catalog_migrates_into_strict_tables_its_quick_check_ok` failed first on the same `strict`
  assertion as 1. `_write_catalog_at_5` now holds Appendix B's extremes (sizes 196 and 28 737 952 534, `source_count` 0
  and 12, duration 32 and 3 576, bitrate 0 and 4 498, the first and last `observed_at`) and one decision per tier, the
  `retracted` one with `target_id = ''`; at the tip it migrates to 15, every table `strict`, `quick_check` `ok` on the
  opener's read-write connection, 2 observations and 4 decisions.
- 4: `test_a_source_holding_a_value_the_destination_refuses_fails_whole_after_a_clean_one`, 12 forgeries in both modes
  (`output`, `into`), 24 cases, each failed first on `Failed: DID NOT RAISE PartialCopyError`: on `main` each merges.
  At the tip each refusal names the forged column: `cannot store TEXT value in INTEGER column files.size_bytes` and
  `observations.source_count` (`'abc'`), otherwise `CHECK constraint failed: <the CHECK>`. The destination equals a
  reference that merged the clean source alone.
- The forging check can fail: with the `files.size_bytes` forgery's `'abc'` mutated to `'123'`, which affinity stores
  as an integer, `_forge` failed on `AssertionError: assert [{'is_as_forged': 0}] == [{'is_as_forged': 1}]`, then
  passed once restored.
- 5: the gate above.

## Departures from the spec

- Acceptance 4 breaks each `CHECK` of D2 once, each instant `CHECK` at one bound (`observations` below the minimum,
  `match_decisions` and `source_observations` above the maximum); acceptance 2 tries both bounds of each.
- Acceptance 3 extends the existing v5 writer, shared with the pre-migration copy tests, rather than adding a second
  one.

## Holistic review

To come.

## Class 1 fixes

- Block 10: the rows the schema refuses that the copier's tests forged before this lot (`_ROWS_THE_SCHEMA_REFUSES`,
  `_BOGUS_ROLE`) never checked what they wrote; they now go through `_forge`.

## Class 2 questions

None.

## Pitfalls

- pytest caches a rewritten test module by its mtime and size: a `sed` mutation of the same length, within the same
  second, reran the stale module until its `.pyc` was deleted.
- A table recreated without `STRICT`: `foreign_keys` off, the copy created under another name, the rows copied, the
  table dropped (its triggers with it), the copy renamed; `) STRICT, WITHOUT ROWID` is replaced before `) STRICT`.
- `?1` binds one value at every place it appears: a forged variant's value and its `content_hash` over it.
- sqlfluff's sqlite dialect parses `STRICT` and `STRICT, WITHOUT ROWID` (`sql-lint` green).
- Serena's Claude Code hook blocks a shell command after several consecutive reads or greps; a blocked command applies
  nothing, so check `git diff --stat` after each scripted edit.

## Not validated

- The integration suites run only in CI's `validate / gate`.
- The patched migrations were not run over a copy of the operator's catalog: acceptance 3 stands on Appendix B's
  measured extremes.

## Next

The closing block 20: section 6's documents (`docs/migration-4x.md`, `docs/operate.md`), the holistic review's
findings, `BACKLOG.md`'s "Every catalog table STRICT" deleted, this handoff corrected. The lot changes the image and
ships with v5, whose tag still waits for the entries under "Must be done before the next release" in `BACKLOG.md`.

## Counts

- Fix-backs: none at writing.
- Cascaded rebases: none at writing.
- Runs re-triggered: see the lead's report.
- Bodies the operator called unreadable: none so far.

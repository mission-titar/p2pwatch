# Handoff: one domain type for arbitrary JSON

Drafted by block 20 from #590 and its own report, for the closing block 30 to correct with the holistic review and its
own report.

## State

Tier Spec lot. Spec `agents/specs/2026-10-31-one-json-value-type.md`, D1 to D7 approved by the operator on 2026-10-31,
from `BACKLOG.md`'s "One domain type for arbitrary JSON". Estimates by `json-text-estimates` (Sonnet); the spec's
reviewers to be named by the closing block.

One stack cut from `main` at `09d21e2c`, three blocks, the closing one included.

| Block | Pull request | Branch |
|---|---|---|
| 10 | #590 | `refactor/json-text-for-source-metadata` |
| 20 | (block 20's) | `refactor/json-text-for-file-metadata` |
| 30 | | `docs/wrap-one-json-text` |

Not merged at writing. What the operator sees (spec section 2): `merge` refuses a source catalog whose file or source
metadata is not the canonical JSON text of an object; in the SQL console a file's `raw_metadata` is an object whose
network names sit under `unmapped`. Nothing else: amuled's answers, the operator's catalog (schema 5, which 0007 folds)
and every page read as before.

## What was built

- **The type** (block 10, D1, D5, D7): `domain/json_object_text.py`'s `JsonObjectText`, a frozen `kw_only` value holding the
  canonical text of a JSON object (`json.dumps(..., ensure_ascii=False, sort_keys=True)`), valid UTF-8, no `NaN` nor
  infinity. Its constructor parses the text, requires an object, writes it back and requires the same text, so any
  other spelling (unsorted or repeated names, other spacing, escapes, `1e999`, a 10 000-level nesting) is refused with
  a `ValueError` saying "a JSON text". `JsonObjectText.from_object(mapping)` writes a mapping and lets the guard check it.
  The domain may import `json` by `loads` and `dumps` only (ast-grep's `domain-imports` and `core-import-names`,
  `AGENTS.md`). Named `JsonText` at first, renamed `JsonObjectText` after the operator's review of #590 (c4d07d24),
  the error messages keeping "a JSON text".
- **The source side** (block 10, D2, D3, D6): `SourceReading.raw_metadata` is a `JsonObjectText`, `SourceMetadata` and its
  walk gone; the mapper builds it with `from_object`; the store writes its text, whose bytes do not move; `merge`
  refuses a source metadata that is not a `JsonObjectText`.
- **The file side** (block 20, D2, D3, D4, D6): `ReportedFile.raw_metadata` is a `JsonObjectText`, defaulting to `{}`,
  `RawMetadata` and `_metadata_texts` gone. `fold_raw_metadata(unmapped, codec=, file_type=, complete_source_count=)`
  returns `{"codec", "complete_source_count", "file_type", "unmapped"}`, the three derived values at the first level
  and under `unmapped` what no field consumes: the result's other keys and, when it holds one no field consumes,
  `media`'s under `media`, every value rendered as text. The mapper's `_unmapped` builds that mapping (surrogates in
  names still replaced). Migration 0007's SQL function `fold_raw_meta` (`variants.py`) reads v4's `[name, value]`
  pairs into the same mapping, a `media.<k>` under `media`, a repeated name keeping its last value; no `.sql` file
  changed. The observation store writes the text, `observation_from_row` reads it back as a `JsonObjectText`, and `merge`
  refuses a file metadata that is not one (`_is_metadata_pairs` gone, one problem text for both sides).

## Evidence

Every block's `uv run poe check` exit 0 at its tip (crawler: 1980 passed, 15 deselected, at block 20).

Budgets against each parent (lines, files; estimate in parentheses): 10, 290 and 17 (350, 17); 20, 327 and 16 (380,
15).

Acceptance:

- 1 and 2 (block 10): `tests/domain/test_json_object_text.py`, first failing on `ModuleNotFoundError: No module named
  'p2pwatch.domain.json_text'` (the name before the rename).
- 3: the source point store's literal, extended with a boolean, an integer and a `null`, passed on `main`'s store
  first (block 10); the observation store's and 0007's literals (block 20) failed first on `TypeError: Object of type
  JsonText is not JSON serializable` (8, the name before the rename) and `MigrationError: migration 7 failed: user-defined function raised
  exception` (9).
- 4 (block 20): `test_a_name_the_network_sends_never_meets_one_the_mapper_derives` failed on `AssertionError: assert
  'Keroro' == 'top'` (the flattened `media.title` overwritten), the `media` cases on `KeyError: 'media'`; 0007's two
  v4 rows (`media.title`, `rating`, `0x0308`; a repeated `0x0308`) and the agreement case with an unmapped `media` key
  in `test_migration_0007.py`.
- 5: the source side failed 20 cases on `main`'s copier (block 10's report lists each refusal). File side (block 20):
  `main`'s check, run on each text, accepts `[]` and the pairs text, refuses every object text as not pairs, and
  raises `RecursionError` on the 10 000-level nesting; at the tip all eleven are refused in both modes with "is not the
  canonical JSON text of an object".
- 6: `git grep -nw -e RawMetadata -e SourceMetadata -e _metadata_texts -e _is_metadata_pairs -e _is_metadata_object --
  packages/` prints nothing at block 20's tip.

## Departures from the spec

- Block 10: `from_object` writes with `allow_nan=True`, so a `NaN` or an infinity reaches the guard and is refused with
  its message; a `JSONDecodeError` is rewrapped like a `RecursionError`, as "a JSON text does not parse".
- Block 20: `unmapped` is always written, `{}` when the result holds no other key (the spec says only that `media`
  appears when it holds such a key); the observation store's test of wire order and duplicates is deleted, the form
  keeping neither.

## Class 1 fixes

None in blocks 10 and 20.

## Class 2 questions

None in blocks 10 and 20.

## Pitfalls

- `_seed` in the copier checks gives the seeded row a random `content_hash`, so a metadata the check wrongly accepts is
  still refused, by the hash check: the test tells them apart only by the message (block 10).
- A catalog a pre-lot v5 build (a `main` image) migrated past 0007 holds the pairs form, which the reader now refuses
  (`ValueError` from `JsonObjectText`) and `merge` refuses; no catalog to keep has passed 0007 (operator, Appendix B).

## Not validated

- The integration suites run only in CI's `validate / gate`.
- 0007's new fold on the operator's catalog: Appendix B's figures (22 distinct metadata, still 22 after D4's fold) were
  measured on a copy on 2026-10-31, not re-run against the code of block 20.

## Next

The lot changes the image and ships with v5. The v5 tag still waits for the four entries under "Must be done before
the next release" in `BACKLOG.md`, the round-trip contracts being the next lot.

## Counts

- Fix-backs: one, the rename in block 10, cascaded onto block 20 by hand (two conflicts, in the merge's check and
  its tests).
- The rest to be filled by the closing block.

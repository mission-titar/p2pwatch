# Handoff: one domain type for arbitrary JSON

Drafted by block 20 from #590 and its own report, corrected by the closing block 30 with the holistic review and its
own report.

## State

Tier Spec lot. Spec `agents/specs/2026-10-31-one-json-value-type.md`, D1 to D7 approved by the operator on 2026-10-31,
from `BACKLOG.md`'s "One domain type for arbitrary JSON". Spec reviewed by `json-value-spec-review`,
`json-value-spec-review-2`, `json-value-spec-review-3` and `json-text-spec-review`; estimates by `json-text-estimates`
(Sonnet); holistic review by `json-text-holistic-review` (`.reviews/one-json-text-holistic.md`).

One stack cut from `main` at `09d21e2c`, three blocks, the closing one included.

| Block | Pull request | Branch |
|---|---|---|
| 10 | #590 | `refactor/json-text-for-source-metadata` |
| 20 | #591 | `refactor/json-text-for-file-metadata` |
| 30 | #592 | `docs/wrap-one-json-text` |

Not merged at writing. What the operator sees (spec section 2): `merge` refuses a source catalog whose file or source
metadata is not the canonical JSON text of an object; in the SQL console a file's `raw_metadata` is an object whose
network names sit under `unmapped`. Nothing else: amuled's answers, the operator's catalog (schema 5, which 0007 folds)
and every page read as before.

## What was built

- **The type** (block 10, D1, D5, D7): `domain/json_text.py`'s `JsonText`, a frozen `kw_only` value holding the
  canonical text of a JSON object (`json.dumps(..., ensure_ascii=False, sort_keys=True)`), valid UTF-8, no `NaN` nor
  infinity. Its constructor parses the text, requires an object, writes it back and requires the same text, so any
  other spelling (unsorted or repeated names, other spacing, escapes, `1e999`, a 10 000-level nesting) is refused with
  a `ValueError` saying "a JSON text". `JsonText.from_object(mapping)` writes a mapping and lets the guard check it.
  The domain may import `json` by `loads` and `dumps` only (ast-grep's `domain-imports` and `core-import-names`,
  `AGENTS.md`).
- **The source side** (block 10, D2, D3, D6): `SourceReading.raw_metadata` is a `JsonText`, `SourceMetadata` and its
  walk gone; the mapper builds it with `from_object`; the store writes its text, whose bytes do not move; `merge`
  refuses a source metadata that is not a `JsonText`.
- **The file side** (block 20, D2, D3, D4, D6): `ReportedFile.raw_metadata` is a `JsonText`, defaulting to `{}`,
  `RawMetadata` and `_metadata_texts` gone. `fold_raw_metadata(unmapped, codec=, file_type=, complete_source_count=)`
  returns `{"codec", "complete_source_count", "file_type", "unmapped"}`, the three derived values at the first level
  and under `unmapped` what no field consumes: the result's other keys and, when it holds one no field consumes,
  `media`'s under `media`, every value rendered as text. The mapper's `_unmapped` builds that mapping (surrogates in
  names still replaced). Migration 0007's SQL function `fold_raw_meta` (`variants.py`) reads v4's `[name, value]`
  pairs into the same mapping, a `media.<k>` under `media`, a repeated name keeping its last value; no `.sql` file
  changed. The observation store writes the text, `observation_from_row` reads it back as a `JsonText`, and `merge`
  refuses a file metadata that is not one (`_is_metadata_pairs` gone, one problem text for both sides).
- **The closing block** (block 30): the holistic review's seven findings fixed (below); `docs/operate.md` (the
  metadata `merge` refuses), `docs/migration-4x.md` (a file's `raw_metadata` an object, its console path) and
  `docs/contributing/architecture.md` (0007's fold under `unmapped`); Appendix B re-measured; the backlog entry
  deleted.

## Evidence

Every block's `uv run poe check` exit 0 at its tip (crawler: 1980 passed, 15 deselected, at block 20; 1981 at block
30). `uv run poe docs-build` exit 0 at block 30. CI's `validate / gate`: run 41244483955 green for #590, 41245540445
green for #591.

Budgets against each parent (lines, files; estimate in parentheses): 10, 290 and 17 (350, 17); 20, 327 and 16 (380,
15); 30, 46 and 8 (20, 3), the review's seven findings beyond the estimate.

Acceptance:

- 1 and 2 (block 10): `tests/domain/test_json_text.py`, first failing on `ModuleNotFoundError: No module named
  'p2pwatch.domain.json_text'`.
- 3: the source point store's literal, extended with a boolean, an integer and a `null`, passed on `main`'s store
  first (block 10); the observation store's and 0007's literals (block 20) failed first on `TypeError: Object of type
  JsonText is not JSON serializable` (8) and `MigrationError: migration 7 failed: user-defined function raised
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
- The reader (block 30): `test_latest_observation_reads_the_raw_metadata_back` records a real fold and reads the
  observation back whole; with `observation_read.py`'s line mutated to `JsonText(text="{}")` it failed on
  `AssertionError: ... raw_metadata=JsonText(text='{}')) != ReportedFile(...`, then passed once the line was restored.
- Appendix B (block 30): block 20's `fold_raw_meta` over a read-only copy of the operator's catalog (`user_version` 5,
  15 763 676 observations), 2026-10-31: 22 distinct stored metadata, 149 distinct inputs once `codec`, `file_type` and
  `complete_source_count` join them, 149 distinct folded texts, no repeated name, no value that is not text. The
  command is in the spec's Appendix B, corrected there.

## Departures from the spec

- Block 10: `from_object` writes with `allow_nan=True`, so a `NaN` or an infinity reaches the guard and is refused with
  its message; a `JSONDecodeError` is rewrapped like a `RecursionError`, as "a JSON text does not parse".
- Block 20: `unmapped` is always written, `{}` when the result holds no other key, a clarification of D4 (which states
  only that `media` appears when it holds such a key): a console query can rely on it, and stage 5's mappers inherit it
  through `fold_raw_metadata`. The observation store's test of wire order and duplicates is deleted, the form keeping
  neither.

## Holistic review

`json-text-holistic-review`: 0 CRITICAL, 1 MAJOR, 6 MINOR, each fixed in block 30.

- MAJOR, no test read a non-empty file metadata back through `observation_from_row` (inherited from `main`): fixed, the
  reader test above.
- MINOR, Appendix B measured with a fold that was not block 20's: fixed, re-measured, the spec marked `(Corrected:
  ...)`. The approved "they stay 22" counted the stored metadata, while the fold's inputs are 149; none merge.
- MINOR, `mapping.py`'s comment on `_MAPPED_KEYS` said "excluded from raw_metadata": fixed, "left out of
  ``unmapped``".
- MINOR, `test_mapping.py`'s docstring cited "D4", which that module uses for the amuleapi spec: fixed, the id dropped.
- MINOR, this handoff named #591 as "(block 20's)": fixed.
- MINOR, `docs/operate.md`, `docs/migration-4x.md` and `docs/contributing/architecture.md` described the old form:
  fixed, `unmapped` always present and a `json_extract` path in `migration-4x.md`.
- MINOR, `test_variants.py`'s `content_hash` cases passed the retired `"[]"`: fixed, `"{}"`.

## Class 1 fixes

None.

## Class 2 questions

None.

## Pitfalls

- `_seed` in the copier checks gives the seeded row a random `content_hash`, so a metadata the check wrongly accepts is
  still refused, by the hash check: the test tells them apart only by the message (block 10).
- On `main`, a source metadata nested past about 10 000 levels made `merge` fail with an unnamed SQLite error (the
  `RecursionError` escaped the SQL function); it is now refused by name (block 10).
- A catalog a pre-lot v5 build (a `main` image) migrated past 0007 holds the pairs form, which the reader now refuses
  (`ValueError` from `JsonText`) and `merge` refuses; no catalog to keep has passed 0007 (operator, Appendix B).
- `fold_raw_meta` reads `codec`, `file_type` and `complete_source_count` beside `raw_meta`: a count of variants 0007
  will build is taken over the four columns, never `raw_meta` alone.
- Serena's Claude Code hook blocks a shell command after several consecutive reads or greps; a blocked heredoc applies
  nothing, so check `git diff --stat` after each scripted edit.

## Not validated

- The integration suites run only in CI's `validate / gate`.

## Next

The lot changes the image and ships with v5. The v5 tag still waits for the four entries under "Must be done before the
next release" in `BACKLOG.md`, the round-trip contracts being the next lot.

## Counts

- Fix-backs: none. Cascaded rebases: none. Runs re-triggered: none (one run per pull request: 41244483955 for #590,
  41245540445 for #591).
- Bodies the operator called unreadable: none so far.
- Friction: the spec went through five reviews by named agents (`json-value-spec-review`, `-2`, `-3`,
  `json-text-spec-review`), and the operator changed the design twice in Discuss, from a recursive `JsonValue` type to
  a `NewType`, then to the value dataclass `JsonText`.

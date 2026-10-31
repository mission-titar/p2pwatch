# Handoff: values checked at the boundary

Drafted by block 30 from the lot's block reports (#581, #582) and its own, then brought up to block 37 from #584,
#585 and its own report, for the closing block 40 to correct with the holistic review.

## State

Tier Spec lot. Spec `agents/specs/2026-10-30-values-checked-at-the-boundary.md`, D1 to D8 approved by the operator on
2026-10-30, D9 to D11 on 2026-10-31 after the holistic review found `merge` unchecked. Found while discussing the
round-trip contracts. Inventory by `boundary-values-inventory` and `merge-boundary-inventory`, estimates by
`boundary-values-estimates` (Sonnet), spec reviewed by `values-at-boundary-spec-review` to
`values-at-boundary-spec-review-4`.

One stack cut from `main` at `ed3eca18`, six blocks, the closing one included.

| Block | Pull request | Branch |
|---|---|---|
| 10 | #581 | `fix/amuleapi-values-cleaned` |
| 20 | #582 | `feat/domain-value-bounds` |
| 30 | #584 | `fix/config-refuses-invalid-text` |
| 35 | #585 | `fix/merge-refuses-invalid-sources` |
| 37 | block 37's | `fix/merge-refuses-inconsistent-rows` |
| 40 | the closing block's | `docs/wrap-values-at-the-boundary` |

Not merged at writing. What the operator sees (spec section 2): `validate-config` and `crawl` refuse a config holding
text that is not valid UTF-8, a control character in a target letter or a rule name, or an environment variable that
is not valid UTF-8, each error saying where. `merge` checks every source before touching the destination, refuses one
holding a value the node could not read back or a row inconsistent with its keys, saying where, and no longer drops a
row in silence. amuled's answers already pass every new check.

## What was built

- **The mapper cleans** (block 10, D1, D2): `mapping.py`'s shared readers replace each surrogate, paired or not, with
  U+FFFD in every text they keep (filename, source name, software, aMule's version, `raw_metadata`'s keys and
  values), and read an integer below 0 or past 2\*\*63 - 1 as they read a malformed one: a count as 0, a duration, a
  bitrate or an id as absent, a search result's size by dropping the result, counted as skipped. An `ecid` of -1 now
  reads as absent, so its detail is no longer asked. Its first commit, the spec's, added `BACKLOG.md`'s "aMule 3.2.0
  pinned" and moved "Round-trip contracts" under "Must be done before the next release"; the block's own extended
  the latter's link to Appendix D.
- **The domain refuses** (block 20, D3): `domain/value_bounds.py` holds `require_well_formed_text` (no surrogate,
  paired or not) and `require_quantity` (an integer in [0, 2\*\*63)), each raising `ValueError` naming its
  `error_label`, `None` passing. `ReportedFile`, `SourceReading`, `DownloadStatus` and `ClientStatus` call them from
  `__post_init__` on each text field (`raw_metadata`'s keys, texts and tuple elements included) and each integer
  field; `raw_metadata`'s integers stay unchecked. Error labels read "a <type>'s <field>"; a refused text is never put
  in the message.
- **Two store tests moved** (block 20, D6): the observation store's surrogate rollback test deleted, with the
  surrogate example of `sqlite_observation_store.py`'s docstring; the source point store's negative-counter test moved
  to `test_append_only.py`, "the catalog's guarantees enforced in SQL", seeded by `tests/support/catalog_rows.py`.
- **The config refuses** (block 30, D4, D5): `load_yaml` walks the loaded tree once and raises `BrokenInputError`
  naming the file and the key path for a text, a key's included, that is not valid UTF-8 (`<file>: search.keywords[1]
  is not valid UTF-8`); `interpolate_document` refuses a referenced variable whose value is not valid UTF-8 with the
  `InvalidConfigError` it raises for an unset one (`amule_api_password: environment variable 'AMULE_API_PASSWORD' is
  not valid UTF-8`), both through `require_well_formed_text`. `catalog_matching`'s `validation.py` refuses a character
  of category `Cc` in a segment letter and a rule name (`segment letter 'a\x1fb' holds a control character`).
  `docs/migration-4x.md` lists the values now refused.
- **`merge` checks every source first** (block 35, D9, D10): `SqliteCatalogCopier` runs a check pass, each source
  attached in turn to a database in memory (`SqliteDatabaseOpener.open_in_memory()`), before `open_catalog` creates or
  migrates the destination, so a refusal writes nothing: the schema version (moved there from the copy, against
  `catalog_version()`), every TEXT column valid UTF-8 (a strict decode of `CAST(x AS BLOB)`, first), `raw_metadata`'s
  shape and texts, no control character in `match_decisions.target_id` and `rule_name` through `has_control_character`,
  made public in `catalog_matching`. A refusal raises `CatalogCopyError` naming the source, the table, the column and
  the first refused row's key (`Merge failed: ... refused: match_decisions.target_id holds a control character, first
  at id 2`), exit 2. The `DecisionReader` port states that a merged catalog's `download` decisions drive the download
  loop, and a test pins it (D10).
- **`merge` refuses inconsistent rows, and drops none in silence** (block 37, D9, D11): the check pass also refuses a
  `files.file_id` or `sources.source_id` its network and native id do not derive (the domain's derivations registered
  as SQL functions, on the known networks) and a variant's `content_hash` that is not the hash of its values; the
  source variants' hash moved from their store into `variants.py` as `source_content_hash`. The copy's `INSERT OR
  IGNORE` became `INSERT ... WHERE true ON CONFLICT DO NOTHING`: a row the destination's schema refuses fails its
  source's transaction, raising `PartialCopyError` (then `PartialMergeError`) that names the table and the sources
  merged before it, which stay; the command line adds `(go on with --into <destination>)`. `docs/operate.md` states
  both.

## Evidence

Every block's `uv run poe check` exit 0 at its tip (crawler: 1762 passed at block 10, 1846 at block 20, 1857 at
block 30, 1891 at block 35, 1911 at block 37, 15 deselected, 100 % coverage).

Budgets against each parent (lines, files; estimate in parentheses): 10, 142 and 3 (175, 4); 20, 349 and 17 (285,
15); 30, 162 and 7 (140, 8); 35, 497 and 10 (330, 11), from a first version of 677 compacted with its behaviour
unchanged; 37, 352 and 15 (195, 9).

Continuous integration, `gh pr checks <n> --required` (2026-10-31): `validate / gate` passes on #581, #582, #584 and
#585. Block 37's run had started at writing.

Acceptance:

- 1 (block 10): the new and extended tests of `test_mapping.py` against `main`'s mapper, 24 failed, 118 passed; at the
  tip, the same functions 36 passed, the module 142. Each case and its failure line are in #581's report.
- 2 (block 20): with the four domain modules restored from block 10 and the new tests kept, 34 failed, 87 passed, each
  `Failed: DID NOT RAISE ValueError`; at the tip, 121 passed. `test_value_bounds.py` first failed on
  `ModuleNotFoundError: No module named 'p2pwatch.domain.value_bounds'`.
- 3 (block 30): the sixteen runs, with `AMULE_API_PASSWORD` set and copies of `deploy/*.yml`, each changed by one
  escape; the eight runs on `main`'s sources (`git archive main` of `crawler/src` and `matching/src`, ahead on
  `PYTHONPATH`) print `Config valid`, exit 0; the eight at block 30's tip exit 1 with one line each, quoted in block
  30's report. The script, `block-30-criterion/run_cases.sh`, is in the lead's scratchpad.
- Block 30's new tests failed first: 9 in the crawler (`DID NOT RAISE BrokenInputError` 7, `DID NOT RAISE
  InvalidConfigError` 2) and 9 in matching (`DID NOT RAISE MatchingConfigError`).
- 4 (blocks 35, 37), through `python -m p2pwatch merge`, the clean source written by the real stores (an observation,
  a decision, three source variants whose `connectable` is true, false and absent), one row seeded per case, `--into`
  into a copy of another node's clean catalog with its `database_digest` read before and after. On `main`'s sources
  every run exits 0, the `'bogus'` row dropped in silence. At the tips, each check case exits 2 naming the source, the
  table and the column, `--output` leaving no file and `--into` the digest unchanged: block 35's five (a filename not
  UTF-8, an escaped `\ud800` in `raw_metadata`, a `raw_metadata` not JSON, a U+001F in a `target_id`, a `\t` in a
  `rule_name`), block 37's four (`file_id`, `source_id`, each variant table's `content_hash`). The `'bogus'` role
  exits 2 naming the table, `--into` unchanged, `--output` left holding no source (Departures). The clean source
  merges to the same digests as on `main`; the clean source then the `'bogus'` one exits 2, names the clean one as
  merged, and leaves the digests of the clean source's merge. The scripts are in the session's scratchpad
  (`b37/build_catalogs.py`, `b37/run_merges.py`).
- Blocks 35 and 37's new tests failed first: every refused value `DID NOT RAISE CatalogCopyError` (26 in block 35, 8
  in block 37), a row the destination refuses `DID NOT RAISE PartialCopyError` (5), and an `ImportError` for each new
  name (`has_control_character`, `open_in_memory`, `catalog_version`, `source_content_hash`).

## Departures from the spec

- Block 10: the tests go past Appendix B's list where the change reaches (aMule's version, the codec, the file type, a
  media key, a nested JSON value, a source's metadata text, a complete-source count, an `ecid` of -1, the limits 0 and
  2\*\*63 - 1); `test_a_non_integer_source_count_reads_as_zero` renamed
  `test_a_malformed_source_count_reads_as_zero`.
- Block 20: `None` passes inside the two functions rather than at each call; the fixture values live in
  `tests/support/domain/value_bounds.py`, shared by five test modules; a new `tests/domain/download/test_status.py`,
  `DownloadStatus` having had no tests of its own.
- Block 30: `load_yaml` checks the keys too, the key path then ending on the refused key, which stderr's
  `backslashreplace` prints escaped (`webui.\ud800 is not valid UTF-8`); D5's messages quote the value with `repr`,
  so a control character prints escaped.
- Block 35: the schema-version refusal moved from the copy pass into the check pass (the value checks name the current
  schema's tables, and a version refusal no longer leaves an empty `--output`); the opener gains `open_in_memory()` and
  `catalog_version()`; the TEXT columns are read from the source's schema, a table the schema does not hold included,
  a refused row named by its primary key or its `rowid`; `raw_metadata`'s texts are checked by dumping the decoded
  JSON back through `require_well_formed_text`; `test_t16` was rewritten there, its mid-copy failure from a
  destination trigger.
- Block 37: criterion 4 asks that `--output` leave no file for the `'bogus'` source too, where Appendix A's D11 design
  leaves the output holding the earlier sources: alone, it leaves an output holding none, the message saying so
  (`keeps the sources merged before it: none`); the `'bogus'` row is seeded with `PRAGMA ignore_check_constraints`, not
  in a source rebuilt without the `CHECK`; `sources.source_id` is checked beside `files.file_id`; the `--into` hint is
  printed in both modes; the id checks guard on the known networks with `CASE`, since SQLite 3.49.1 was seen
  evaluating `network IN (...)` first even when written second; the check pass registers every catalog SQL function,
  `iso_to_micros` included.

## Class 1 fixes

- Block 10: `BACKLOG.md`'s "Round-trip contracts" entry said "amended by Appendix B" of this lot's spec; it now names
  Appendix D, as D7 states.
- Blocks 20 to 37: none.

## Class 2 questions

None in blocks 10 to 37.

## The holistic review

`values-at-boundary-holistic` found `merge` unchecked before the closing block: the operator decided D9 to D11 on
2026-10-31, which blocks 35 and 37 hold. The rest is to be written by the closing block.

## Counts

To be written by the closing block: fix-backs, cascaded rebases and the runs they re-triggered.

## Pitfalls

- The editing tools decode an escaped U+FFFD and an escaped surrogate pair written in a file into the characters
  themselves; a lone surrogate escape stays as written. Spell U+FFFD `"\N{REPLACEMENT CHARACTER}"`, keep a pair as two
  adjacent literals or as a YAML escape behind a doubled backslash, and check the bytes of every file written, config
  copies included (blocks 10, 20, 30).
- A pytest node id holding a surrogate or a space cannot be passed back on the command line: select with `-k`
  (block 10).
- The mapper keeps its own surrogate pattern and integer bound, the same as `value_bounds`' private ones: the mapper
  replaces where the domain refuses (block 20).
- `PYTHONPATH` takes precedence over the workspace's editable installs, so `main`'s sources from `git archive` run
  with the branch's interpreter; print each package's `__file__` to prove which ran (block 30).
- `open_reader` on a WAL catalog leaves its `-wal` and `-shm` beside it, and the test helper `count()` opens through
  `open_catalog`, creating the file it counts: a test that a refused merge wrote nothing reads the digest first and
  asserts `not destination.exists()` (block 35).
- An append-only table refuses `UPDATE`: seed one bad value with an `INSERT ... SELECT` copy of a row, a text not
  UTF-8 as `CAST(x'...' AS TEXT)`, a row a `CHECK` refuses under `PRAGMA ignore_check_constraints = ON` (a `NOT NULL`
  cannot be bypassed so); SQLite stores NULL in a `BLOB PRIMARY KEY` left out of an insert (blocks 35, 37).
- A crafted source holding a `sources.native_id` its network refuses is refused before any write, but with SQLite's
  generic `cannot check source catalog <path>: user-defined function raised exception`, `SourceKey` refusing it inside
  the `source_id` SQL function (block 37).

## Not validated

- Against a real amuled, which sends no such value (Appendix C). amuleapi's error messages (a refusal's, a bulk
  outcome's) are not cleaned: they are no mapper text, and reach only stderr, whose `backslashreplace` cannot fail.
- The integration suites run only in CI's `validate / gate`.
- D8: the lead re-runs Appendix C's two queries on the operator's catalog before the node upgrades to v5.
- The merge's check pass on a catalog of the operator's size: it scans the variants and decisions, never the
  observations (Appendix C measured 96 to 115 ms per 20,000 variants, the four checks it timed together); the
  operator's catalog, at schema 5, holds no variant.

## Next

The lot changes the image. D7: no v4 backport, the v4 node stays stopped until v5, and the v5 tag waits for the three
entries under "Must be done before the next release" in `BACKLOG.md` (aMule 3.2.0 pinned, the Grype scan back, the
round-trip contracts). The round-trip contracts are the next lot, before "Test quality" (Appendix D).

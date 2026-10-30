# Handoff: values checked at the boundary

Drafted by block 30 from the lot's block reports (#581, #582) and its own, for the closing block 40 to correct with
the holistic review.

## State

Tier Spec lot. Spec `agents/specs/2026-10-30-values-checked-at-the-boundary.md`, approved by the operator on
2026-10-30. Found while discussing the round-trip contracts. Inventory by `boundary-values-inventory`, estimates by
`boundary-values-estimates` (Sonnet), spec reviewed by `values-at-boundary-spec-review`,
`values-at-boundary-spec-review-2` and `values-at-boundary-spec-review-3`.

One stack cut from `main` at `ed3eca18`, four blocks, the closing one included.

| Block | Pull request | Branch |
|---|---|---|
| 10 | #581 | `fix/amuleapi-values-cleaned` |
| 20 | #582 | `feat/domain-value-bounds` |
| 30 | block 30's | `fix/config-refuses-invalid-text` |
| 40 | the closing block's | `docs/wrap-values-at-the-boundary` |

Not merged at writing. What the operator sees (spec section 2): `validate-config` and `crawl` refuse a config holding
text that is not valid UTF-8, a control character in a target letter or a rule name, or an environment variable that
is not valid UTF-8, each error saying where. amuled's answers already pass every new check.

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

## Evidence

Every block's `uv run poe check` exit 0 at its tip (crawler: 1762 passed at block 10, 1846 at block 20, 1857 at
block 30, 15 deselected, 100 % coverage).

Budgets against each parent (lines, files; estimate in parentheses): 10, 142 and 3 (175, 4); 20, 349 and 17 (285,
15); 30, 162 and 7 (140, 8).

Continuous integration, `gh pr checks <n> --required` (2026-10-30): `validate / gate` passes on #581 and #582. Block
30's run had started at writing.

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

## Class 1 fixes

- Block 10: `BACKLOG.md`'s "Round-trip contracts" entry said "amended by Appendix B" of this lot's spec; it now names
  Appendix D, as D7 states.
- Blocks 20, 30: none.

## Class 2 questions

None in blocks 10 to 30.

## The holistic review

To be written by the closing block.

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

## Not validated

- Against a real amuled, which sends no such value (Appendix C). amuleapi's error messages (a refusal's, a bulk
  outcome's) are not cleaned: they are no mapper text, and reach only stderr, whose `backslashreplace` cannot fail.
- The integration suites run only in CI's `validate / gate`.
- D8: the lead re-runs Appendix C's two queries on the operator's catalog before the node upgrades to v5.

## Next

The lot changes the image. D7: no v4 backport, the v4 node stays stopped until v5, and the v5 tag waits for the three
entries under "Must be done before the next release" in `BACKLOG.md` (aMule 3.2.0 pinned, the Grype scan back, the
round-trip contracts). The round-trip contracts are the next lot, before "Test quality" (Appendix D).

# Handoff: values checked at the boundary

Drafted by block 30 from #581, #582 and its own report, brought up to block 37 from #584 to #586, then corrected by
the closing block 40 with both holistic reviews and the reports of #587 and #588.

## State

Tier Spec lot. Spec `agents/specs/2026-10-30-values-checked-at-the-boundary.md`, D1 to D8 approved by the operator on
2026-10-30, D9 to D11 on 2026-10-31 after the first holistic review found `merge` unchecked. Found while discussing the
round-trip contracts. Inventory by `boundary-values-inventory` and `merge-boundary-inventory`, estimates by
`boundary-values-estimates` (Sonnet) for rows 10 to 37 and by `block-40-closing` for rows 38 to 40, spec reviewed by
`values-at-boundary-spec-review` to `values-at-boundary-spec-review-4`.

One stack cut from `main` at `ed3eca18`, eight blocks, the closing one included: the closing block passed the 20-file
bound (about 29 files) and split into blocks 38, 39 and 40.

| Block | Pull request | Branch |
|---|---|---|
| 10 | #581 | `fix/amuleapi-values-cleaned` |
| 20 | #582 | `feat/domain-value-bounds` |
| 30 | #584 | `fix/config-refuses-invalid-text` |
| 35 | #585 | `fix/merge-refuses-invalid-sources` |
| 37 | #586 | `fix/merge-refuses-inconsistent-rows` |
| 38 | #587 | `fix/values-at-the-boundary-review` |
| 39 | #588 | `fix/merge-review` |
| 40 | #589 | `docs/wrap-values-at-the-boundary` |

Not merged at writing. What the operator sees (spec section 2): `validate-config` and `crawl` refuse a config holding
text that is not valid UTF-8, a control character in a target letter or a rule name, an environment variable that is
not valid UTF-8, or an alias of a value that holds it, each error saying where. `merge` checks every source before
touching the destination, refuses one holding a value the node could not read back or a row inconsistent with its
keys, saying where, copies each source whole or not at all, no longer drops a row in silence, attaches its sources
read-only, and leaves no `--output` that no source entered. amuled's answers already pass every new check.

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
  merged before it, which stay. `docs/operate.md` states both.
- **The first review's findings** (block 38): `value_bounds` exposes `is_quantity` and `replace_surrogates`, on which
  `require_quantity` and the mapper build, the mapper's copies of both bounds gone. `load_yaml`'s walk carries the
  containers enclosing it and refuses an alias of a value that holds it (`search.keywords[1] refers to a value that
  holds it`), where it ended in a `RecursionError`, as the interpolation already did on `main`; a key of a path has its
  non-printable characters escaped. The rest is tests and words: a negative `ed2k_user_id`'s case, each text refusal
  matched on its own field, `subtree` for a YAML subtree, `NOT_WELL_FORMED_TEXTS`, the docs quoting the lines
  `validate-config` prints.
- **`merge` after the second review** (block 39): each source attached read-only (`file:<path>?mode=ro`), every
  connection `SqliteDatabaseOpener` returns opening a quoted `file:` URI, since SQLite reads an attached name as a URI
  only on such a connection. A new `--output` that no source entered is removed and the error is a plain
  `CatalogCopyError`, so `PartialCopyError` always names a merged source, and only then, with `--output`, the command
  line prints `(go on with --into <output> <output> and the sources not merged)`. The check pass registers only the
  four functions its checks call, none memoized, its `source_id` giving `NULL` for a key `SourceKey` refuses; the
  checks are a `kw_only` dataclass, `_RowCheck`, each condition written once with its column.
- **The closing block** (block 40): `AGENTS.md`'s invariant "the node supports UTF-8 text only", the amuleapi gotcha on
  what amuleapi writes, and the invariant "`merge` writes only to its destination" made exact; `BACKLOG.md`'s "Every
  catalog table STRICT" moved under "Must be done before the next release" and extended to what D9 leaves it,
  "Round-trip contracts" trimmed to two lines; D7's `(Corrected: ...)` beside stage 1's D16, the umbrella spec's
  "Release" line and stage 3 row, and the keyword-only handoff's "Next"; the spec's `(Corrected: ...)` lines.

## Evidence

Every block's `uv run poe check` exit 0 at its tip (crawler: 1762 passed at block 10, 1846 at block 20, 1857 at
block 30, 1891 at block 35, 1911 at block 37, 1929 at block 38, 1935 at blocks 39 and 40, 15 deselected, 100 %
coverage).

Budgets against each parent (lines, files; estimate in parentheses): 10, 142 and 3 (175, 4); 20, 349 and 17 (285,
15); 30, 162 and 7 (140, 8); 35, 497 and 10 (330, 11), compacted from 677 (Departures); 37, 352 and 15 (195, 9); 38,
181 and 15 (200, 16); 39, 373 and 11 (325, 13); 40, 11 and 2 (30, 2).

Continuous integration, `gh pr checks <n> --required` (2026-10-31): `validate / gate` passes on #581, #582, #584,
#585, #586, #587 and #588; #589's run started with its pull request.

Acceptance:

- 1 (block 10): the new and extended tests of `test_mapping.py` against `main`'s mapper, 24 failed, 118 passed; at the
  tip, the same functions 36 passed, the module 142. Each case and its failure line are in #581's report.
- 2 (block 20): with the four domain modules restored from block 10 and the new tests kept, 34 failed, 87 passed, each
  `Failed: DID NOT RAISE ValueError`; at the tip, 121 passed. `test_value_bounds.py` first failed on
  `ModuleNotFoundError: No module named 'p2pwatch.domain.value_bounds'`.
- 3 (block 30): the sixteen runs, with `AMULE_API_PASSWORD` set and copies of `deploy/*.yml`, each changed by one
  escape; the eight runs on `main`'s sources (`git archive main` of `crawler/src` and `matching/src`, ahead on
  `PYTHONPATH`) print `Config valid`, exit 0; the eight at block 30's tip exit 1 with one line each, quoted in #584's
  report. The script, `block-30-criterion/run_cases.sh`, is in the lead's scratchpad. Block 38 added the alias cycle,
  `error: <c.yml>: search.keywords[1] refers to a value that holds it`, exit 1 (#587).
- Block 30's new tests failed first: 9 in the crawler (`DID NOT RAISE BrokenInputError` 7, `DID NOT RAISE
  InvalidConfigError` 2) and 9 in matching (`DID NOT RAISE MatchingConfigError`).
- 4 (blocks 35, 37, 39), through `python -m p2pwatch merge`, the clean source written by the real stores (an
  observation, a decision, three source variants whose `connectable` is true, false and absent), one row seeded per
  case, `--into` into a copy of another node's clean catalog with its `database_digest` read before and after. On
  `main`'s sources every run exits 0, the `'bogus'` row dropped in silence. At the tips, each check case exits 2 naming
  the source, the table and the column, `--output` leaving no file and `--into` the digest unchanged: block 35's five
  (a filename not UTF-8, an escaped `\ud800` in `raw_metadata`, a `raw_metadata` not JSON, a U+001F in a `target_id`,
  a `\t` in a `rule_name`), block 37's four (`file_id`, `source_id`, each variant table's `content_hash`). The
  `'bogus'` role alone exits 2 naming the table, `--into` unchanged; with `--output` block 37 left an output holding
  no source, and block 39 leaves no file and prints no hint. The clean source merges to the same digests as on
  `main`; the clean source then the `'bogus'` one exits 2, names the clean one as merged, and leaves the digests of the
  clean source's merge, the hint printed with `--output` only (block 39). A source carrying a pending `-wal` merges
  with both its files' sha256 unchanged at block 39's tip, where its parent rewrote the source and deleted the `-wal`.
  The scripts are in the session's scratchpad (`b37/build_catalogs.py`, `b37/run_merges.py`, `b39/`).
- Blocks 35 and 37's new tests failed first: every refused value `DID NOT RAISE CatalogCopyError` (26 in block 35, 8
  in block 37), a row the destination refuses `DID NOT RAISE PartialCopyError` (5), and an `ImportError` for each new
  name (`has_control_character`, `open_in_memory`, `catalog_version`, `source_content_hash`).
- Block 38's new tests failed first: `ImportError` for `is_quantity`, `RecursionError` for the three alias cases, an
  `AssertionError` for the three key cases; the `ed2k_user_id` case and the exact labels, which pass on the parent,
  each failed under a mutation not committed.
- Block 39's new tests failed first: the read-only attach `unable to open database: file:...?mode=ro`, the pending
  `-wal` `FileNotFoundError` after the merge, a first refused source `PartialCopyError is CatalogCopyError`, the
  refused `sources.native_id` SQLite's generic `user-defined function raised exception`, the hint printed in both
  modes; the URI quoting and `_quoted`, which pass on the parent, each failed under a mutation not committed. The
  check pass's tracemalloc peak over one source fell from 9.2 MB at 20,000 variants and 49.2 MB at 100,000 to 0.1 MB.

## Departures from the spec

- Block 10: the tests go past Appendix B's list where the change reaches (aMule's version, the codec, the file type, a
  media key, a nested JSON value, a source's metadata text, a complete-source count, an `ecid` of -1, the limits 0 and
  2\*\*63 - 1); `test_a_non_integer_source_count_reads_as_zero` renamed
  `test_a_malformed_source_count_reads_as_zero`.
- Block 20: `None` passes inside the two functions rather than at each call; the fixture values live in
  `tests/support/domain/value_bounds.py`, shared by five test modules; a new `tests/domain/download/test_status.py`,
  `DownloadStatus` having had no tests of its own.
- Block 30: `load_yaml` checks the keys too, the key path then ending on the refused key, which stderr's
  `backslashreplace` printed escaped (block 38 escapes it in the message itself); D5's messages quote the value with
  `repr`, so a control character prints escaped.
- Block 35: a first version measured 677 lines, past the 500-line bound, and was compacted to 497 (the checks as
  positional tuples, the JSON's texts dumped back through `require_well_formed_text`, one parametrized test, shorter
  docstrings) where the workflow says a block past a bound splits and offers no compaction. The second review found
  the tuples cost readability where blocks 35 and 37 meet; block 39 made them a `kw_only` dataclass, and the operator
  chose no re-split (2026-10-31). Also: the schema-version refusal moved from the copy pass into the check pass (the
  value checks name the current schema's tables, and a version refusal no longer leaves an empty `--output`); the
  opener gains `open_in_memory()` and `catalog_version()`; the TEXT columns are read from the source's schema, a table
  the schema does not hold included, a refused row named by its primary key or its `rowid`; `test_t16` was rewritten
  there, its mid-copy failure from a destination trigger.
- Block 37: the `'bogus'` row is seeded with `PRAGMA ignore_check_constraints`, not in a source rebuilt without the
  `CHECK`; the id checks guard on the known networks with `CASE`, since SQLite 3.49.1 was seen evaluating `network IN
  (...)` first even when written second. Three departures block 39 reversed: a refused first source left an
  `--output` holding none, where criterion 4 asks for no file; the `--into` hint was printed in both modes; the check
  pass registered every catalog SQL function, `iso_to_micros` included.
- Block 38: the names the review left open (`replace_surrogates`, `_require_well_formed_tree`, `_printable_key`), and
  the message "refers to a value that holds it", the review's "refers to itself" being inexact; `load_yaml`'s
  docstring drops its note on `safe_load`'s dates and objects.
- Block 39: the `COMMIT` runs after the copy statements through the helper that rolls back and names the place; the
  copier registers its check functions itself, `variants.py` making its two by-position hash wrappers public for it;
  only `source_id` gets a `NULL`-returning variant (`FileKey` refuses no `native_id`, and the `CASE` guard keeps an
  unknown network for the destination's `CHECK`); option A's removal runs in a `finally`, so a first source
  interrupted otherwise leaves no output either, while a `cannot open output` failure is unchanged; the port's
  docstring reads "raises `CatalogCopyError` before any source is copied, or `PartialCopyError` after one, the sources
  copied kept"; `decision_reader.py`'s "(download §5)" dropped rather than restored.
- Block 40: `AGENTS.md`'s UTF-8 invariant names `merge` beside the config and the mapper, Appendix A's wording
  predating D9; the spec's D10 now precedes D11.

## Class 1 fixes

- Block 10: `BACKLOG.md`'s "Round-trip contracts" entry said "amended by Appendix B" of this lot's spec; it now names
  Appendix D, as D7 states.
- Blocks 20 to 40: none.

## Class 2 questions

None in blocks 10 to 40. The operator decided the exits the reviews left open (below), the fan-out alias tree an
accepted limit on 2026-10-31: only the config's author can write one.

## The holistic reviews

**First review** (`values-at-boundary-holistic`, `.reviews/values-at-the-boundary-holistic.md`), over
`origin/main...origin/fix/config-refuses-invalid-text`: no CRITICAL, no MAJOR, sixteen MINOR. Its `merge` finding
became D9 to D11 (the operator, 2026-10-31), blocks 35 and 37; the closing block took the backlog's and the
handoff's, block 38 the rest.

| # | Finding | Exit |
|---|---|---|
| 1 | the mapper's copies of the two bounds | fixed, block 38: `is_quantity`, `replace_surrogates` |
| 2 | `docs/operate.md`'s `error:` list | fixed, block 38, the alias cycle listed too |
| 3 | `merge` copies another catalog's rows unchecked | fixed, blocks 35 and 37: D9 to D11 |
| 4 | `docs/migration-4x.md`'s three forms | fixed, block 38, the three lines quoted whole |
| 5 | `packages/matching/AGENTS.md`'s list of refusals | fixed, block 38 |
| 6 | a refused key written raw in its message | fixed, block 38, non-printable characters escaped |
| 7 | a self-referencing alias ends in a `RecursionError` | fixed, block 38, refused in one line |
| 7b | an alias tree that fans out costs exponential time in both walkers | accepted limit (operator), spec section 7 |
| 8 | the source point store's comment on `OR IGNORE` | fixed, block 38 |
| 9 | the `D1:` and `D2:` prefixes in `test_mapping.py` | fixed, block 38 |
| 10 | `\w+` in the text refusals' label match | fixed, block 38 |
| 11 | `node` for a YAML subtree | fixed, block 38, `interpolation.py` too |
| 12 | `MALFORMED_TEXTS` | fixed, block 38: `NOT_WELL_FORMED_TEXTS` |
| 13 | `_connectable`'s untested negative `ed2k_user_id` | fixed, block 38 |
| 14 | "Round-trip contracts" spans four lines | fixed, block 40 |
| 15 | `load_yaml`'s six-line docstring | fixed, block 38 |
| 16 | the handoff's row 30 and its CI line | fixed, block 40 |

**Second review** (`.reviews/values-at-the-boundary-holistic-2.md`), over
`origin/main...origin/fix/merge-refuses-inconsistent-rows`, weighted on blocks 35 and 37: one MAJOR, twelve MINOR. The
operator decided three exits on 2026-10-31: option A for the MAJOR, no re-split of block 35, the sources read-only.

| # | Finding | Exit |
|---|---|---|
| 1 | MAJOR: a refused first source left an empty `--output`, against criterion 4 | fixed, block 39: option A, the output removed |
| 2 | block 35's compaction: positional tuples, SQL formatted twice | fixed, block 39: `_RowCheck`; no re-split; a departure above |
| 3 | `merge` writes to its sources: a detach checkpoints a pending `-wal` | fixed, block 39: attached read-only |
| 4 | the check pass memoizes `content_hash` without bound | fixed, block 39: four functions, none memoized |
| 5 | a refused `sources.native_id` names no table, column or row | fixed, block 39: `source_id` gives `NULL` |
| 6 | the `--into` hint is not a working command | fixed, block 39, with `--output` only |
| 7 | `_COPY_STEPS`, one of them the commit | fixed, block 39: `_COPY_STATEMENTS` |
| 8 | `_check_catalog`'s docstring | fixed, block 39 |
| 9 | the port's "before any write" | fixed, block 39 |
| 10 | a bare "(D11)" and "(download §5)" | fixed, block 39, both dropped |
| 11 | the handoff: four v5 conditions, STRICT's gap, CI, `source_id`, the compaction, D10 before D11 | fixed, block 40 |
| 12 | `docs/operate.md`'s `expected 12` | fixed, block 39: `expected 15` |
| 13 | `_quoted` has no test | fixed, block 39: the table `no"tes` |

## Counts

- Fix-backs: none. Cascaded rebases: none, each pull request's timeline holding no force push and each branch one run.
- Runs re-triggered: one. #584's push started no run, and the lead fired it by closing and reopening the pull request
  (2026-10-30, 20:07 UTC). One re-triggered run for eight blocks.
- The lead's session was cut on 2026-10-31, during the lot.
- No pull request body called unreadable at writing; the operator has not read the stack yet.

## Pitfalls

- The editing tools decode an escaped U+FFFD and an escaped surrogate pair written in a file into the characters
  themselves; a lone surrogate escape stays as written. Spell U+FFFD `"\N{REPLACEMENT CHARACTER}"`, keep a pair as two
  adjacent literals or as a YAML escape behind a doubled backslash, and check the bytes of every file written, config
  copies included (blocks 10, 20, 30).
- A pytest node id holding a surrogate or a space cannot be passed back on the command line: select with `-k`
  (block 10).
- `PYTHONPATH` takes precedence over the workspace's editable installs, so `main`'s sources from `git archive` run
  with the branch's interpreter; print each package's `__file__` to prove which ran (block 30). `python -I` ignores
  `PYTHONPATH`: such a probe runs with `python -P` (block 39).
- `open_reader` on a WAL catalog leaves its `-wal` and `-shm` beside it, and the test helper `count()` opens through
  `open_catalog`, creating the file it counts: a test that a refused merge wrote nothing reads the digest first and
  asserts `not destination.exists()` (block 35). A read-only attach leaves them too, beside a source in WAL mode, its
  own bytes unchanged (block 39).
- An append-only table refuses `UPDATE`: seed one bad value with an `INSERT ... SELECT` copy of a row, a text not
  UTF-8 as `CAST(x'...' AS TEXT)`, a row a `CHECK` refuses under `PRAGMA ignore_check_constraints = ON` (a `NOT NULL`
  cannot be bypassed so); SQLite stores NULL in a `BLOB PRIMARY KEY` left out of an insert (blocks 35, 37).
- SQLite reads an attached file name as a URI only on a connection opened with URIs: `ATTACH 'file:...?mode=ro'`
  fails with `unable to open database` otherwise (probed on SQLite 3.54.0). On such a connection, `ATTACH` and `VACUUM
  INTO` read any name starting with `file:` as a URI; the pre-migration copy's, derived from the catalog's path, is
  absolute in production (block 39).

## Not validated

- Against a real amuled, which sends no such value (Appendix C). amuleapi's error messages (a refusal's, a bulk
  outcome's) are not cleaned: they are no mapper text, and reach only stderr, whose `backslashreplace` cannot fail.
- The integration suites run only in CI's `validate / gate`.
- D8: the lead re-runs Appendix C's two queries on the operator's catalog before the node upgrades to v5.
- The merge's check pass on a catalog of the operator's size: it scans the variants and decisions, never the
  observations (Appendix C measured 96 to 115 ms per 20,000 variants, the four checks it timed together); the
  operator's catalog, at schema 5, holds no variant.
- A source in a directory where SQLite cannot create its `-shm`, which a read-only attach of a WAL source needs
  (block 39).

## Next

The lot changes the image, and ships with v5: D7 leaves v4 without a backport, its node stopped until v5.

1. Before the operator's node upgrades to v5, the lead re-runs Appendix C's two catalog queries on it (D8).
2. The v5 tag waits for the four entries under "Must be done before the next release" in `BACKLOG.md`:
   - the round-trip contracts, the next lot, before "Test quality" (Appendix D);
   - every catalog table STRICT, which this lot relies on to close what D9 left to it: a value of the wrong type in
     any column (a text or a real in an `INTEGER` column, a blob in a `TEXT` one), a negative size, count, duration or
     bitrate (a source's received bytes aside, which a `CHECK` already holds), a `tier` outside `DecisionTier` and
     `retracted`, and an instant in micros outside `datetime`'s range, all of which `merge` copies until then;
   - aMule 3.2.0 pinned;
   - the Grype scan back on p2pwatch, one leg per image.

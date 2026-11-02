# Handoff: a file's size stored once

Drafted by block 70's teammate from the block reports of #615, #616, #618, #619, #620 and #621 and its own, corrected
and completed by the closing block's teammate (block 80).

## State

Tier Spec lot. Spec `agents/specs/2026-11-02-file-size-stored-once.md`, D1 to D7 decided by the operator on 2026-11-02,
from `BACKLOG.md`'s "A file's size stored once", which block 10's first commit moved under "Must be done before the
next release". Survey by `size-once-survey`, estimates by `size-once-estimates` (Sonnet), spec reviewed by
`size-once-spec-review`, holistic review by `size-once-holistic-review`. Corrected after approval by the closing
block, each marked `(Corrected: ...)` in the spec: acceptance 3 and 4 (read through the timeline), section 6's line
references, Appendix A's block 10 (the rule's keyless wording, the copier's comment and test name), block 30 (the
counts test kept) and block 40 (the port's docstrings and the contract unchanged).

Cut from `main` at `ac1c5aae`, eight blocks, the closing one included, all open:

| Block | Pull request | Branch |
|---|---|---|
| 10 | #615 | `fix/insert-on-conflict` |
| 20 | #616 | `refactor/variant-without-size` |
| 30 | #618 | `refactor/file-size-from-latest-observation` |
| 40 | #619 | `refactor/source-pages-best-filename` |
| 50 | #620 | `refactor/queued-download-without-size` |
| 60 | #621 | `refactor/downloads-table-without-size` |
| 70 | #622 | `refactor/tier-rise-link-in-notifier` |
| 80 | #623 | `docs/wrap-file-size-stored-once` |

What the operator sees (spec section 2): the file page's timeline has no size column, the page giving the size above
it (30); in the SQL console, `observation_variants` (20) and `downloads` (60) have no `size_bytes`, a file's size being
`files.size_bytes`; a tier rise notification reads as before, its body unchanged (70); the upgrade to v5 adds no
migration and no pre-migration copy (acceptance 16); a catalog a pre-lot v5 build took past 0008 fails the crawler's
first observation write instead of losing every observation silently (10).

## What was built

- **`ON CONFLICT` everywhere** (block 10, D7): the observation store's three inserts and migration 0007's two end in
  `ON CONFLICT (<key>) DO NOTHING`, `WHERE true` before it where the `SELECT` would otherwise read the `ON` as a join's.
  The gate keeps `OR IGNORE` out: sqlfluff's `CV09` (`blocked_words = "ignore"`) in the `.sql` files, the ast-grep rule
  `no-or-ignore` (`(?i)\bOR\s+IGNORE\b`) in every Python string, and an `AGENTS.md` Hard rule.
- **A variant without the size** (block 20, D1, D2): catalog migrations 0007 and 0008 edited in place, the variants'
  `content_hash` on seven columns (Python, its SQL registration, the merge copier's check), every observation reading
  its size from `files`; v4 variants that differed by size alone fold into one under 0007.
- **A listed file always observed** (blocks 30 and 40, D3, D4): `CatalogEntry` and `FileHistory` lose `size_bytes`,
  their `latest_observation` mandatory; the latest-observation query inner-joins, so a `files` row without an
  observation leaves the files list, `read_file_history` gives `None` (a 404), and the source pages leave out its
  periods, `best_filename_by_file` holding every period's file and the webui's short-hash fallback gone.
  `FileJudge.rejudge` raises a `RuntimeError` naming the file in place of its fallback. The file page's timeline rows
  hold four cells.
- **local.db without the size** (blocks 50 and 60, D5, D2): `TrackedDownloadWriter.record_queued` loses `size_bytes`,
  the fake store its `sizes`; local migration 0014 rebuilds `downloads` without the column.
- **The link built by the notifier** (block 70, D6): `TierRise` carries its `file: FileKey` in place of `ed2k_link`,
  the policy no longer imports `build_ed2k_link`, and `AppriseNotifier`'s `_rise_body` builds the link from the rise's
  file, filename and size (the `match` on the network moved with it).
- **The closing block** (80): the holistic findings fixed (below), `FileJudge.rejudge` raising before any write and
  `ObservationReader` promising the size its file was first recorded at, with its contract test;
  `docs/contributing/architecture.md` and `docs/migration-4x.md` written after the lot; "A file's size stored once"
  deleted from `BACKLOG.md`.

## Evidence

`uv run poe check` exit 0 at every block's tip, each report's first line; crawler passed (15 deselected each): 2071
(10), 2073 (20), 2067 (30, 40, 50), 2068 (60, 70, 80: one contract test added, the 0002 test deleted).
`uv run poe docs-build` at block 80's tip: `No issues found`.

Budget against each block's parent (lines, files; the spec's estimate in parentheses): 10, 97 and 11, `BACKLOG.md`
included (about 110, 10); 20, 165 and 16 (170, 16); 30, 248 and 19, the two files past the estimate being the class 1
fix (about 190, 17); 40, 55 and 6 (about 85, 8); 50, 83 and 13 (about 85, 13); 60, 40 and 5 (about 20, 4); 70, 35 and 6
(50, 6); 80, 91 and 14 (25, 3: the estimate left no room for the review's nine findings).

Acceptance, each new behaviour watched failing before its implementation:

- 1 (20): `test_open_catalog_keeps_a_file_s_size_in_files_alone`, `Left contains one more item: {'table_name':
  'observation_variants'}`.
- 2 (20): `test_content_hash_sql_function_matches_the_python_one` with seven arguments, `sqlite3.OperationalError:
  wrong number of arguments to function content_hash()`.
- 3 (20): `test_a_version_5_file_reported_at_two_sizes_migrates_into_one_variant_read_at_its_size`,
  `{'variant_count': 2} != {'variant_count': 1}`; 0007 alone,
  `test_old_rows_differing_by_size_alone_become_one_variant`, `{'variant_count': 2, 'observation_count': 2} !=
  {'variant_count': 1, 'observation_count': 2}`.
- 4 (20): `test_two_reports_differing_by_size_alone_are_one_variant_read_at_the_first_size`, `assert 2 == 1` on the
  variant count.
- 5 (10): `test_a_variant_breaking_a_not_null_fails_the_write_and_writes_no_row`, `Failed: DID NOT RAISE
  PersistenceError`.
- 6 (10): `sql-lint` with `CV09` before 0007 changed, `L: 37 | P: 11 | CV09 | Use of blocked word 'IGNORE'.` and the
  same on line 67, nothing else; `ast-grep scan` with the rule on `main`'s store, four errors (its docstring, line 1,
  and its statements, lines 35, 38, 45) plus `tests/support/catalog_rows.py:54`.
- 7 (10): the rule's tests, proved by mutating the rule since `ast-grep test` passes a test naming no rule: without
  `(?i)`, `FAIL no-or-ignore` on `insert or ignore`; a space for `\s+`, `Error: test failed. 16 passed; 1 failed;`,
  exit 4.
- 8 (30): the contract's two value tests built without `size_bytes`, `TypeError: CatalogEntry.__init__() missing 1
  required keyword-only argument: 'size_bytes'`, the same for `FileHistory`.
- 9 (30, 40): `test_read_catalog_entries_leaves_out_a_file_never_observed`, `Left contains one more item:
  'dddddddddddddddddddddddddddddddd'`; `test_file_history_of_a_file_never_observed_is_none`, `assert FileHistory(...,
  size_bytes=42, observations=(), latest_observation=None, ...) is None`;
  `test_a_page_leaves_out_the_periods_on_a_file_never_observed` (both histories), `Left contains one more item:
  FileKey(network=<Network.ED2K: 'ed2k'>, native_id='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')`.
- 10 (40): mypy, `Argument "best_filename" to "_file_sharing_period_display" has incompatible type "str | None";
  expected "str"`, at both callers.
- 11 (30): `test_a_file_never_observed_raises_naming_it_and_dispatches_nothing`, `Failed: DID NOT RAISE RuntimeError`;
  renamed `..._before_any_write` by block 80, its added `count_decisions(catalog_connection) == 1` failing `assert 2 ==
  1` against block 70's judge, which committed the retraction before raising.
- 12 (30): `test_file_page_timeline_shows_each_observation_as_one_plain_line` and
  `test_file_page_says_when_no_observation_falls_in_the_interval` against the old template, the four-cell row and
  `<td colspan="4">` absent; the `Size` `<dd>` asserted in
  `test_file_page_shows_the_network_the_native_id_the_size_and_the_ed2k_link`.
- 13 (60): `test_a_created_local_db_has_no_size_bytes_on_its_downloads` and
  `test_a_v4_local_db_migrated_keeps_its_downloads_without_their_size`, `AssertionError: assert 'size_bytes' not in
  {'bytes_done', 'completed_at_micros', ...}`; `test_0014_converts_each_download_stamp_to_micros_and_keeps_a_null` on
  its `SELECT *` comparison.
- 14 (50): every `record_queued` call without `size_bytes` against the old port, 44 failed with `TypeError:
  SqliteTrackedDownloadStore.record_queued() missing 1 required keyword-only argument: 'size_bytes'`; mypy `Missing
  named argument "size_bytes" for "record_queued" of "TrackedDownloadWriter"  [call-arg]` at each call.
- 15 (70): the tests building `TierRise` with `file=` and no `ed2k_link`, against the old value, `TypeError:
  TierRise.__init__() got an unexpected keyword argument 'file'` at the collection of `test_apprise_notifier.py` and
  `test_policy.py`. `test_a_rise_names_its_tier_its_targets_its_file_and_its_link` keeps its expected body, link
  included, now that the rise carries no link: the notifier builds it.
- 16 (60, 70): at each tip, 15 catalog and 15 local migration files under `origin/main`'s names, `copy-before` on the
  same ones (catalog 0005, 0006, 0007, 0008, 0011, 0015; local 0004, 0005, 0006, 0007, 0010, 0011, 0014, 0015);
  block 70 by `diff` of `git ls-tree --name-only` and of `git grep -l copy-before` between `origin/main` and `HEAD`,
  both empty.
- 17: the gate above; CI's `validate / gate` passed on #615 to #622 (`gh pr checks <n> --required`, 2026-11-02, each
  `validate / gate pass`), #623's run started when block 80 stopped.
- Block 80's contract test, `test_a_later_report_at_another_size_is_read_at_the_file_s_first_size`, run against block
  10's store, whose variants still carried their size, in a detached worktree removed after: `Differing attributes:
  ['reported_file']`, the report being the size alone; green at block 80's tip.

## Departures from the spec

- **Block 10**: `AGENTS.md` and the rule's message say `ON CONFLICT ... DO NOTHING`, not `ON CONFLICT (<key>) DO
  NOTHING`, since the merge copier's six inserts are keyless; the store and 0007 name their keys, as D7 says. In
  `test_sqlite_catalog_copier.py` the `OR IGNORE` was a comment and a test name:
  `test_t2_merge_overlapping_identity_files_or_ignore` became `..._keeps_one`.
- **Block 20**: acceptance 1 checks every catalog table, only `files` having a `size_bytes`; acceptances 3 and 4 read
  both observations back through `observation_read.observations_between`, the store's reader giving only the latest
  and the best; a test of 0007 alone beside acceptance 3.
- **Block 30**: `read_file_history` reads the file from its latest observation's row (`SELECT_LATEST_OBSERVATION` by
  `file_id`), one query fewer, `_SQL_FILE` gone. `test_read_matched_and_total_file_counts_counts_file_with_no_observation`
  stays, pinning section 7's accepted limit. Deleted with the state: the two never-seen sort tests and the search
  filter's exclusion test. The webui's never-seen display test became
  `test_catalog_entry_displays_shows_the_latest_filename_and_source_count`. The port says "the observed files"; no
  contract test states the absence, which no Writer can produce.
- **Block 40**: the adapter's absence test seeds an observed file beside the one never observed, so a reader dropping
  every period fails it too; `source_reader_contract.py` unchanged, its history tests already comparing the whole
  `best_filename_by_file`; the webui tests' `_UNSEEN` became `_OTHER_FILE`. The promise sits in the field comment of
  `best_filename_by_file` on both histories, not in the port's docstrings as Appendix A has it, a docstring holding two
  lines at most (the fix-back, `4e0fdd31`).
- **Block 50**: none; the contracts lose the `draw_quantity` the size took, which shifts their later draws (seeded per
  test).
- **Block 60**: a test from a version-5 local.db holding a download, for acceptance 13's "v4 local.db migrated", the
  existing 0014 test starting from version 13; `test_migration_0002.py` keeps `test_user_version_is_at_least_two`.
- **Block 70**: none.
- **Block 80**: the judge's guard is not the review's `if not filenames` after `read_known_filenames`: the decisions
  to write are computed first and, when there are any, the best observation is read before the first write. The
  review's form would have kept the `best is None` guard for the type, reachable only by a variant without an
  observation and raising after the writes again; this one keeps D3's and acceptance 11's wording ("when it finds no
  best observation") and adds no read when nothing changed. The contract test the review called optional is written,
  `AGENTS.md`'s "the port is the reference" asking a contract test of every promise.

## Holistic review

`size-once-holistic-review` over `git diff origin/main...origin/refactor/tier-rise-link-in-notifier` (`ac1c5aae` to
`2143605d`, 12 commits, 67 files, +1019 -500), report `.reviews/size-once-holistic.md`: CRITICAL 0, MAJOR 0, MINOR 9.
It read the spec, this draft, the full diff and the seven block reports, re-ran acceptance 16 (the same 15 files and
`copy-before` list on `origin/main` and the top) and ran three probes (below). Each finding and its exit, all fixed in
block 80:

| # | Finding | Exit |
|---|---|---|
| MINOR 1 | `FileJudge.rejudge` raised only after `record_decision` had written the changed decisions, so on its bug path a retraction was committed and never notified; its docstring said it raised on any file never observed | Fixed: the guard before the first write (Departures, block 80), the test asserting no decision row added, the docstring at two lines saying a change on a file never observed raises |
| MINOR 2 | The port and the glossary's `observation` promised a read "whole", a report at another size reading back at its file's first | Fixed: `ObservationReader`'s docstring and the glossary row add "at the size its file was first recorded at", with the contract test above |
| MINOR 3 | `test_migration_0002.py`'s one test, `user_version >= 2`, tested nothing of local 0002 | Fixed: the module and its `tests_without_unit` entry deleted; `test_open_local_creates_the_tables_and_versions_the_schema` asserts `user_version == 15` |
| MINOR 4 | The files counter's comment hid that it counts a file never observed | Fixed: "Without a `search_text` it joins no observation, so it also counts a file never observed, which the list leaves out" |
| MINOR 5 | "never seen" and "seen file" beside the lot's "never observed" | Fixed: three docstrings of `observation_read.py` and one of `sqlite_catalog_scan_reader.py` |
| MINOR 6 | `variants.py` kept `fold_raw_meta`'s spelling because 0007 "never changes", which the lot edited twice | Fixed: "The SQL name keeps the spelling migration catalog/0007 calls." |
| MINOR 7 | `architecture.md` and `migration-4x.md` not yet written after the lot (section 6, deferred to block 80) | Fixed: the inserts by `ON CONFLICT DO NOTHING`, never `INSERT OR IGNORE`; a variant without the size; the domain validating first because its error names the value; `migration-4x.md`'s console bullet, the size by `JOIN files USING (file_id)` |
| MINOR 8 | Spec claims the departures made false, no `(Corrected: ...)` | Fixed: the corrections listed under State |
| MINOR 9 | This handoff stale | Fixed: State, Evidence, Not validated and this section |

The review's probes, in detached worktrees of `origin/main` and the top under the scratchpad (removed after), each
worktree's `src` first on `sys.path`, which settle section 2's last point and section 7's merge limits:

1. `main`'s store writes one observation into a new catalog; the top's store then records another file:
   `PersistenceError NOT NULL constraint failed: observation_variants.size_bytes`, `files 1 variants 1 observations 1`
   after. The write fails and leaves no `files` row (section 2, D7).
2. The top's `python -m p2pwatch merge --output out.db prelot.db`: `Merge failed: source catalog .../prelot.db refused:
   observation_variants.content_hash is not the hash of its variant's values, first at variant_id 1`, no `out.db`
   written (section 7, "a pre-lot catalog as a source is already refused").
3. The top's `merge --into prelot.db prelot.db fresh.db`: `copy of .../fresh.db failed at observation_variants: NOT
   NULL constraint failed: observation_variants.size_bytes`, the destination unchanged (section 7, "`merge --into` it
   fails on its variants' size").

## Class 1 fixes

- Block 10: the hash guard's comment in `test_sqlite_observation_store.py` gave `OR IGNORE` as its reason; it now says
  the guard's error names the hash, where the `CHECK`'s names its expression.
- Block 30: `short_timestamp`'s empty-input branch, its docstring paragraph and its test (`6d06e1cd`): both callers
  pass a `datetime.isoformat()`, so only tests reached it.
- Block 60: `tests_without_unit` described `test_migration_0002.py` as a catalog migration's test; it opens a local.db.

## Class 2 questions

None, blocks 10 to 80.

## Pitfalls

- **`ast-grep test` passes a test file naming no rule** (10): prove a rule's tests by mutating the rule (`BACKLOG.md`'s
  "A rule test naming no rule fails the gate").
- **`ALTER TABLE` adds no `NOT NULL` column without a default** (10): acceptance 5's test rebuilds the empty variants
  table from its own `sqlite_schema` text, so a later column change does not touch it.
- **An upsert after a `SELECT` with no `WHERE`** needs `WHERE true`, or SQLite reads its `ON` as a join's; 0007's
  observations insert ends on `ORDER BY` and needs none (10).
- **`ruff format` drops the parentheses around a lone string** even when the line then passes 100 columns, and `E501`
  fails: a long SQL constant stays in two parts (20).
- **Serena's `replace_symbol_body` on a dataclass** (pyrefly 1.4.0) drops the `@dataclass` line and duplicates the last
  field's trailing comment: edit a class's fields with `replace_content` (30).
- **The list's join to the latest observation must be inner** like the CTE's: a `LEFT JOIN` hands
  `observation_from_row` a row of `NULL`s (30).
- **`uv run poe fix` exits 1 on its first run** when `ruff check --fix` meets a line the formatter folds afterwards; the
  second run is green (40).
- **A red run's open SQLite connection** shows as a `PytestUnraisableExceptionWarning` `ERROR` in a later test, gone
  with the red state (50).
- **Removing one keyword from many calls**: `replace_in_files` over
  `(\.record_queued\((?:[^()]|\([^()]*\))*?)size_bytes=[^,]+,\s*`, dry run first, left the other `size_bytes=` alone
  (50).

## Not validated

- The integration suites, the compose smoke's seeded download row included (60), run only in CI's `validate / gate`.
- Migrations 0007 and 0008 at the scale of the operator's catalog (15.8 million observations): their `SELECT`s are
  unchanged but for one column fewer in 0007's `DISTINCT`, and the upsert takes the uniqueness check `OR IGNORE` took;
  not timed (10, 20).
- 0008 at exactly version 7 on two variants differing by size alone, which section 7 expects to fail: not probed.
- The query plans on the operator's catalog: the plan test passes on the test catalog, and the spec review's
  `EXPLAIN QUERY PLAN` covered the inner joins on a current-schema catalog (30).
- A rise sent to a real service: its body is unit-tested against `FakeApprise`, unchanged from `main` (70).

## Next

The lead rebases the stack onto the current `main` and the operator reads and merges it (`gh stack merge --rebase`).
The lot changes what the image ships, but the v5 tag still waits for "aMule 3.2.0 pinned" (#614 open) and "The Grype
scan back on p2pwatch".

## Counts

From the lead's record:

- Fix-backs: 1, block 40 (`4e0fdd31`): a port docstring past two lines, its promise moved into
  `best_filename_by_file`'s field comments.
- Cascaded rebases: none.
- Runs re-triggered: 1, #619's first run, cancelled by the fix-back's push. Fewer runs re-triggered than blocks (8).
- Bodies the operator called unreadable: none so far.
- Splits: none.

## Friction

For the lead's report:

- The lead's spec wrote `AGENTS.md`'s rule with a key (`ON CONFLICT (<key>) DO NOTHING`) the merge copier's six
  keyless inserts could not follow, which section 6 already worded without one.
- The spec made acceptance 3 and 4 read both observations back through a port read that does not exist: the reader
  gives only the latest and the best, so block 20 read the timeline.
- The spec asked block 40 for port docstrings that could not hold in two lines: the fix-back.
- Block 30 came to 19 files, one below the bound, its class 1 fix taking the two past the estimate.
- The closing block's estimate (25 lines, 3 files) left no room for the review's findings: 91 lines, 14 files.

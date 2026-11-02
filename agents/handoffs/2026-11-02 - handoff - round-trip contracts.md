# Handoff: round-trip contracts

Drafted by block 130's teammate from the block reports of #596 to #609 and its own; the closing block corrects it.

## State

Tier Spec lot. Spec `agents/specs/2026-11-01-round-trip-contracts.md`, D1 to D8 decided by the operator on 2026-10-29,
2026-10-30 and 2026-11-01, from `BACKLOG.md`'s "Round-trip contracts", under "Must be done before the next release".
Survey by `round-trip-survey`, estimates by `round-trip-estimates` (Sonnet), spec reviewed by `round-trip-spec-review`.
Corrected after approval, each marked `(Corrected: ...)` in the spec: D4 (plain random draws, 2026-11-01, after blocks
20 and 30 first built the distinctness by construction, `5b9f2591`), acceptance 5 with it, the deletions' exemption
(the holistic review checks every mapping, no mutation proof) and block 40 split into 40 and 45 (`70cee85c`).

Cut from `main` at `49ddd7fe`, fifteen blocks, the closing one included, all open at this draft:

| Block | Pull request | Branch |
|---|---|---|
| 10 | #596 | `refactor/contract-port-fixtures` |
| 20 | #597 | `test/observation-store-contract` |
| 30 | #599 | `test/decision-store-contract` |
| 40 | #600 | `test/source-point-store-contract` |
| 45 | #601 | `test/source-point-reads-contract` |
| 50 | #602 | `test/scan-and-coverage-reader-contracts` |
| 60 | #603 | `fix/file-search` |
| 70 | #604 | `test/file-listing-and-history-contract` |
| 80 | #605 | `test/file-count-contract` |
| 90 | #606 | `fix/source-search` |
| 100 | #607 | `test/sharing-period-contract` |
| 110 | #608 | `test/source-history-contract` |
| 120 | #609 | `test/drawn-values-in-local-contracts` |
| 130 | to open | `test/node-state-reader-contract` |
| 140 | to open | `docs/wrap-round-trip-contracts` |

What the operator sees (spec section 2): the search of the webui's files and sources pages is literal (`%` and `_`
match only themselves) and ignores case and accents (`ecole` and `ÉCOLE` find `école`). Nothing else: at block 130's
tip, `git diff --stat origin/main...HEAD -- '*/migrations/*' deploy/ '*/webui/templates/*'` prints nothing.

## What was built

- **Ports as fixtures** (block 10, D3, C1): every contract receives each port it uses through an abstract fixture of
  its own (`writer`, `reader`, `observation_writer`...), each test's parameters typed by the ports; the nine pair
  contracts' `<Thing>Ports` are gone (`AmuleConfStoreContract`'s second store became `unreadable_reader`).
- **The draws** (blocks 20, 30, 40, 45, 100, 120, D4, C2): a `randomness` fixture in `tests/conftest.py`,
  `random.Random(request.node.nodeid)`; `tests/support/draws.py` (`draw_text` of 8 to 64 characters over a wide
  alphabet, `draw_quantity`/`draw_quantities` below 2\*\*62, `draw_instant`/`draw_instants` to the microsecond over a
  century, the plural forms distinct and ascending), and a `draw_<value>` at the mirror of each value's module:
  `tests/support/domain/observation.py` (`draw_file`, `draw_reported_file`, `draw_file_observation`,
  `draw_observed_file`), `file_target_decision.py` (`draw_target_id(s)`, `draw_decision_record`,
  `draw_dated_decision`), `source.py` (`draw_source_key`, `draw_source_reading`, `draw_source_point`,
  `draw_point_read_again`), `download/status.py` (`draw_download_status`), `search/backoff.py` (`draw_backoff_key`,
  `draw_backoff_state`, the delay below 10\*\*9 s). Each draw module has its own test, listed in `tests_without_unit`.
- **Eight new contracts** (Appendix A), each with its SQLite subclass in the implementation's own test module, seeded
  only through the Writers: `ObservationStoreContract` (20), `DecisionStoreContract` (30), `SourcePointStoreContract`
  (40, 45), `CatalogScanReaderContract` and `CoverageReaderContract` (50), `CatalogFileReaderContract` (60, 70, 80),
  `SourceReaderContract` (90, 100, 110), `NodeStateReaderContract` (130). The four existing contracts over `local.db`
  moved to drawn values (120). Twelve SQLite subclasses in all; the eight stub or spy doubles exempted by name in
  `test_contract_subclasses.py`.
- **The literal search** (blocks 60, 90, D5): `instr(fold_for_search(<column>), fold_for_search(:search_text))`, `> 0`
  for a substring, `= 1` for a hash prefix; `fold_for_search` (casefold, NFD, combining marks stripped) in
  `persistence_sqlite/search_fold.py`, registered by `SqliteDatabaseOpener.open_reader` alone (Departures).
- **The promises written into the ports** (D6, Appendix B, and the ones the blocks added, Departures): acceptance 3's
  table below.
- **Adapter tests deleted** (D7): 107 functions, each mapped to its contract test in its block's report (Appendix D
  estimated 106: `test_observation_read.py` 6 rather than 7, block 50 keeping the iteration test;
  `test_sqlite_source_reader.py` 20 rather than 18). Four adapter tests added where a contract cannot seed or D6 keeps
  a tie with its adapter: the candidates' same-instant tie (30), the never-seen sort (70), the periods started by one
  reading (100), a page's file never observed (110). `catalog_seeds.py` deleted (100).

## Evidence

`uv run poe check` exit 0 at every block's tip, each report's first line; at block 130's tip (`246cd714`): every
package at 100 %, crawler 2065 passed, 15 deselected (2020 on `main`), 0 of 212 crawler modules short of their own
tests.

Budget against each block's parent (lines, files; the spec's estimate in parentheses; past 500 only by deleted adapter
tests, under the spec's exemption, the rest given after the slash): 10, 570 and 29, mechanical exemption (about 490,
30); 20, 599/396 and 14 (629); 30, 615/387 and 8 (553); 40, 245 and 6 (about 340); 45, 440 and 5 (about 410); 50,
550/428 and 9 (449); 60, 638/482 and 11 (554); 70, 653/426 and 6 (546); 80, 428 and 4 (355); 90, 451 and 5 (356);
100, 512/296 and 7 (452); 110, 691/455 and 4 (733); 120, 319 and 11 (315); 130, 409 and 5 (457).

Acceptance:

- 1: `pytest --collect-only -q --no-cov` at block 130's tip lists tests under the twelve SQLite subclasses
  (`TestSqlite...`: `BackoffStateStore` 5, `CatalogFileReader` 36, `CatalogScanReader` 6, `CoverageReader` 9,
  `DecisionStore` 12, `NodeIdStore` 3, `NodeStateReader` 7, `ObservationStore` 8, `PolicyFingerprintStore` 3,
  `SourcePointStore` 13, `SourceReader` 37, `TrackedDownloadStore` 11). Each new subclass deleted or renamed away made
  `test_contract_subclasses.py` fail naming its implementation (blocks 20, 30, 40, 50, 60, 90, 130), and each missing
  exemption naming its double.
- 2: every swap of Appendix E fails at least one contract test (first lines in each block's report: 20, 30, 40, 45, 50,
  60, 70, 80, 90, 100, 110, 120, 130). The files list's `duration_seconds` and `bitrate_kbps` swap fails
  `test_an_entry_holds_its_first_size_...` and `test_an_entry_s_latest_observation_...`: `E       assert
  CatalogEntry(...'download'>))) == CatalogEntry(...'download'>)))` (block 60). A swap of an instant with a
  quantity shows as `E       OverflowError: date value out of range`.
- 3: the table below, line numbers at `246cd714`.
- 4: blocks 60 and 90, the `%`, `_`, `ÉCOLE` and `ecole` cases failing first against `main`'s `LIKE`, the `\` and
  ASCII cases passing there; `EXPLAIN QUERY PLAN` unchanged by the fold (60, 90).
- 5: the draws' own tests; the grep prints nothing over each contract over a database (exit 1 in every report).
- 6: each report's table, every deleted test and its contract test.
- 7: `git grep -nE 'class [A-Z][A-Za-z]*Ports\b' -- packages` prints nothing (exit 1, blocks 10, 110, 130).
- Mutants beyond the spec's: each block ran 5 to 34 more against its contract (method: the mutant alone in the tree,
  `__pycache__` cleared, `PYTHONDONTWRITEBYTECODE=1`, the loaded module checked to hold it, the file restored). Those
  that also passed the parent's whole crawler suite, now caught by a contract: the latest observation from a variant's
  oldest sighting (20), the candidates' same-instant tie (30, by a new adapter test), `MIN` for `MAX` in the latest
  point (45), the search on any filename (60), the sort tie-break following the direction, `NULLS LAST`, `NULLS
  FIRST`, the tier sort on `MIN` (70), seven count mutants (80), the sources' tie-break descending, the latest name
  from the last recorded variant (90), two identity mutants of the periods (100), 14 history mutants, a fifteenth equivalent (110), a
  file-blind `is_tracked` and `read_queued_target_id`, the delay stored to the millisecond (120), the downloads by
  `native_id DESC`, by `queued_at_micros DESC` or unordered, the backoffs by `client_name DESC`, the progress stamped
  on its first growth only (130).

### Acceptance 3: the promises

| Port line | Promise | Contract test | Failing line (mutant) |
|---|---|---|---|
| `observation_reader.py:19-20` | `read_best_observation`: `None` for a file never observed | `ObservationStoreContract::test_a_file_never_observed_has_no_observation_and_no_filename` | `E       TypeError: 'NoneType' object is not subscriptable` (the `None` check dropped) |
| `decision_reader.py:22-23` | `read_download_candidates`: a file's by target id | `DecisionStoreContract::test_a_file_s_candidates_come_in_target_id_order` | `E       assert (DownloadCand...k_ïE&zàÔq$#')) == (DownloadCand..."~PœnP\'Nßé'))` (`target_id DESC`) |
| `catalog_file_reader.py:47-48` | `read_file_count_by_tier`: a tier no file holds is absent, not 0 | `CatalogFileReaderContract::test_a_tier_counts_each_file_holding_a_current_decision_of_it_once_or_is_absent` | `E       AssertionError: assert {<DecisionTie...download'>: 3} == {<DecisionTie... 'notify'>: 2}` (every tier counted) |
| `catalog_entry.py:12-13`, `:29`; `file_history.py:13` | the size the file was first observed with (the entry, the history, the size sort) | `test_an_entry_holds_its_first_size_...`, `test_a_history_holds_the_first_size_...`, `test_a_sort_on_the_observations_orders_on_its_value_then_on_file_id[size-*]` | `E       assert FileHistory(f...>Ñ"1zß0!=<ô')) == FileHistory(f...>Ñ"1zß0!=<ô'))`; `E       AssertionError: assert [FileKey(netw...671e29'), ...] == [FileKey(netw...125ce1'), ...]` (the latest observation's size) |
| `catalog_entry.py:31`, `file_history.py:15`, `coverage_reader.py:15-16` | the legacy retraction of no target left out | `CatalogFileReaderContract::test_the_legacy_retraction_of_no_target_is_left_out`, `::test_a_history_leaves_out_the_legacy_retraction_of_no_target`, `CoverageReaderContract::test_the_legacy_retraction_of_no_target_is_left_out` | Appendix B's mutant (`target_id <> ''` dropped) is equivalent (Departures); `PARTITION BY md.file_id` fails each: `E   assert {"\|K'3曹σ🐸gHΣ*...: 'notify'>,)} == {'OES ïx9-Bσ🐸...: 'notify'>,)}` (coverage) |
| `catalog_file_reader.py:15-17`, `source_reader.py:13-14` | D5's search, literal, case and accents ignored; for sources a hash's start or any name carried | `CatalogFileReaderContract::test_the_search_finds_a_filename_holding_the_text_as_typed_case_and_accents_ignored[*]`, `SourceReaderContract::test_the_search_finds_a_name_..._ignored[*]`, `::test_the_search_finds_the_start_of_a_user_hash_..._ignored[*]`, `::test_the_search_reads_every_name_a_source_carried_and_lists_what_it_finds_whole` | `main`'s `LIKE`: `E       AssertionError: assert {FileKey(netw...6cc657efd2c')} == {FileKey(netw...ee80632f605')}`; the fold without its accents stripped: `E       AssertionError: assert set() == {FileKey(netw...517734bb4a5')}` |
| `node_state_reader.py:13-14` | downloads by when queued, then by native id; backoffs by client, the whole-client one before its channels, then by channel | `NodeStateReaderContract::test_the_downloads_are_read_by_when_they_were_queued_then_by_native_id`, `::test_the_backoffs_are_read_by_client_each_whole_client_backoff_before_its_channels` | `native_id DESC`: `E       assert (TrackedDownl..._reason=None)) == (TrackedDownl..._reason=None))`; `channel DESC`: `E       assert [(BackoffKey(...nds=968497)))] == [(BackoffKey(...nds=651844)))]` |
| `sharing_period.py:22-25`, `source_reader.py:46-47` | a period cut on a gap past `window.gap`, a drop of the received bytes, a change of variant; its received bytes the growth while sending | `SourceReaderContract::test_a_gap_past_the_window_s_gap_cuts_a_period_and_a_gap_at_it_does_not`, `::test_a_drop_of_the_session_s_received_bytes_cuts_a_period`, `::test_a_change_of_role_or_of_reading_cuts_a_period_even_when_the_variant_comes_back`, `::test_only_a_sending_period_received_bytes_their_growth_over_it[*]` | gap: `E       AssertionError: assert (SharingPerio...)[жgu6@kÊ.'),) == (SharingPerio...😀)[жgu6@kÊ.'))`; drop: `E       AssertionError: assert (SharingPerio...aケ:ÙOロÉ[}7'),) == (SharingPerio...σaケ:ÙOロÉ[}7'))`; variant: `E       AssertionError: assert (SharingPerio...AC%œœÙwàÊtH')) == (SharingPerio...AC%œœÙwàÊtH'))`; while sending: `E       assert (SharingPerio...cPa/";)ÈœJ'),) == (SharingPerio...cPa/";)ÈœJ'),)`; the latest count: `E       AssertionError: assert (SharingPerio...σaケ:ÙOロÉ[}7')) == (SharingPerio...σaケ:ÙOロÉ[}7'))` |
| `source_point_reader.py:25-26` | `read_latest_point`: `since` included, `before` excluded | `SourcePointStoreContract::test_the_latest_point_is_read_from_since_included_to_before_excluded` | `>`: `E       assert None == LatestPoint(role=<SourceRole.QUEUED: 'queued'>, ...)`; `<=`: `E       AssertionError: assert LatestPoint(r...9415346472681) == LatestPoint(r...6515558719397)` |

Promises the blocks added beyond Appendix B's rows (D6, an order stated whole or a value a page shows): the sort's
direction, null placement and `file_id` tie-break (70, `CatalogEntrySort` and the port), the sources list's
`source_id` tie-break (90), the histories' name ties, best filename and "whenever read" (110,
`source_history.py:25-27`, `:37-39`, `source_reader.py:31-32`, `:38-40`); their failing lines are in the reports.

## Departures from the spec

- **The draws' API**, which the spec leaves open, as listed under What was built; the relations are keyword arguments
  (`file=`, `observed_at=`, `filename=`, `source_count=`, `bytes_done=`, `client_name=`...), and a twin or a sighting
  seen again is built by `dataclasses.replace` (20, 70, 90). Texts a test needs distinct are drawn plainly and sorted,
  not without replacement (30). The search cases and the user hash write their texts, the relation they test (60, 90).
- **`fold_for_search` is registered by `open_reader` alone** (60), where Appendix A has `register_sql_functions`
  register it on every connection: only the readers search, and `register_sql_functions` on a reader would hand the
  SQL console the memoized `content_hash` and `fold_raw_meta`, whose cache a query grows without bound, and
  `iso_to_micros`, which only migrations may call. A comment in `open_reader` keeps the reason.
- **Appendix B's legacy retraction mutant is equivalent** in the coverage, the listing, the history and the counts (50,
  60, 70, 80): v4 wrote its no-target row only as a retraction, which `tier IN (...)` already leaves out. The promise
  is stated and tested; `PARTITION BY md.file_id` is the mutant that fails it.
- **Promises written into the domain types the ports return** rather than the port lines: `CatalogEntry` and
  `FileHistory` (the first size, the legacy retraction), `CatalogEntrySort` (the sort keys), `SharingPeriod` (the cut
  rules and the growth), `source_history.py` (60, 70, 100, 110). Ties stated where the webui pages through them (90,
  110), kept unstated with an adapter test where it reads the whole (100).
- **Equivalent mutants under SQLite's plan**: the candidates' `ORDER BY` dropped (30), the sources' and the histories'
  tie-break dropped (90, 110): the tests record against the listed order, so another plan fails them.
- **Kept adapter tests beyond Appendix D's**: `test_observation_read.py`'s iteration test (50: the order by native id,
  a `files` row without an observation, and `observation_read` covered by its own tests).
- **Helpers**: block 50 moved `draw_observed_file` into `tests/support` (its third user); block 120 left
  `_draw_queued_file` private to the tracked downloads' contract, and block 130 built its own `_queue`, which returns
  the `TrackedDownload` as read before any listing.
- **Block 130**: the contract also tests `TrackedDownload.latest_progress_at`, the latest listing whose bytes grew,
  which the domain type states (its name and "None until its bytes grow") rather than a port line; the progress
  stamped on its first growth only passed the parent's whole suite. No "aware in UTC" promise for `NodeStateReader`,
  as for the catalog readers of this lot: equality with drawn aware instants refuses a naive one.
- **Files past a row's count**, each block's `pyproject.toml` (`tests_without_unit`) and the docstrings the promises
  went into; block 10's 18 subclass modules where section 6 says 19.

## Holistic review

To be filled by the closing block: the review over `git diff origin/main...origin/test/node-state-reader-contract`,
which also checks every row of every deletion mapping (the deletions' exemption), each finding with its exit.

## Class 1 fixes

- Block 20: three sentences D8 made stale (`AGENTS.md`'s subclass bullet, `testing.md`'s opening sentence on contracts,
  `_EXEMPTIONS`' comment), which named only doubles breaking their port on purpose.
- Block 30: an adapter test of the candidates' same-instant tie, tested nowhere (`id ASC` passed the parent's suite).
- Block 70: `test_observation_read.py`'s `_raw` and `_observation` lose parameters no call passed; `_seed_sortable`'s
  docstring.
- Block 120: the tracked downloads' contract queues a second file in two tests (a file-blind `is_tracked` and
  `read_queued_target_id` passed the whole suite).
- Block 130: `SqliteTrackedDownloadStore.set_state`'s docstring said "any other call" clears `failure_reason`; another
  `set_state` or `set_completed` does, `set_seen` leaves it (Appendix B).

## Class 2 questions

None in any block.

## Pitfalls

- **A stale `.pyc`** (Appendix E): a module restored or mutated to the same size within the same second runs its old
  bytecode. Clear `__pycache__` and set `PYTHONDONTWRITEBYTECODE=1`; check the loaded module holds the mutant (its
  string constants, and its functions' bytecode, `co_code`, since a swap of two locals leaves `co_names` unchanged).
- **A `StrEnum` member equals and hashes as its text** (`DecisionTier`, `DownloadState`, `WaitingReason`,
  `SourceRole`): neither `==`, a dict nor a `Counter` tells a stored text from the member; only `is` or a type check.
- **An instant swapped with a quantity** fails as `OverflowError: date value out of range`, not as an assertion.
- **A draw a test relates must be given**: `draw_source_point` draws a node per point, `draw_point_read_again` its
  received bytes, `draw_source_reading` a name, `draw_download_status` the bytes; a test needing them shared or ordered
  passes them, or a mutant survives on the draw.
- **A test's roles assigned in `file_id` order hide a mutant** (70): draw the roles, record apart from the order read.
- **`git grep` skips untracked files**: acceptance 5's grep over a new contract prints nothing before its first commit.
- **Serena's `safe_delete_symbol`** leaves a deleted function's trailing inline comment behind (60, 70, 80); it does not
  delete module constants (110). Read the diff's `+` lines after a deletion.
- **zsh does not word-split an unquoted `$files`**: a loop passing several test paths to pytest silently collects
  nothing; use `bash` or `${=files}` (10).
- **Parametrize ids holding a space** are undercounted by a probe parsing `FAILED (\S+)`; read the summary line (90).
- **Readers on `ThreadReadConnections` see the Writers' rows** only because `SqliteDatabaseOpener` opens every
  connection in autocommit (50).

## Not validated

- The integration suites run only in CI's `validate / gate`.
- The fold's cost on the node's catalog: Appendix E's 7 ms is by proportion from an isolated bench; the plans were
  checked unchanged (60, 90), not timed on the node.

## Next

The closing block (140): the holistic review's findings, `docs/migration-4x.md`'s literal search (section 8),
`BACKLOG.md`'s "Round-trip contracts" deleted, this handoff corrected. Then, per `BACKLOG.md`, the v5 tag still waits
for "aMule 3.2.0 pinned" and "The Grype scan back on p2pwatch"; "Test quality" decides how a contract's tests count
under its unique-coverage rule.

## Counts

To be confirmed by the closing block from the lead's record.

- Fix-backs: two seen in the history, blocks 20 and 30 reworked for D4's correction (`6f4a1dbc`, `b9dbe3e4`).
- Cascaded rebases: at least the one that carried block 30 and the blocks above onto block 20's fix-back.
- Runs re-triggered: two, by `gh run list --workflow PR` per branch at this draft: block 20 ran on `a397eebd` then
  `6f4a1dbc`, block 30 on `0f86466d` then `b9dbe3e4` (one more run cancelled); every other branch ran once, green.
- Bodies the operator called unreadable: none reported in the blocks.

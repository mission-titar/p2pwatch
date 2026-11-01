# Round-trip contracts

Tier Spec. Discussed with the operator on 2026-11-01, from `BACKLOG.md`'s "Round-trip contracts", under "Must be done
before the next release". Earlier Discusses settled part of it: Appendix B of
`agents/specs/2026-10-29-rows-read-by-column-name.md` and Appendix D of
`agents/specs/2026-10-30-values-checked-at-the-boundary.md`; this spec restates what it keeps and says what it revises.

## 1. In short

Eleven ports of `persistence_sqlite` have no contract, which eight contracts cover: the pairs
`ObservationWriter`/`ObservationReader`, `DecisionWriter`/`DecisionReader`, `SourcePointWriter`/`SourcePointReader`,
and the readers `CatalogFileReader`, `CatalogScanReader`, `CoverageReader`, `NodeStateReader`, `SourceReader`. The
readers' adapter tests seed by raw SQL, every one of them picks its values by hand, and a swap they miss passes
today: `duration_seconds` and `bitrate_kbps` swapped by alias in the files list's query leave the crawler's 2020 unit
tests green (Appendix E).

The lot writes a contract for each, seeded only through the Writers with drawn values, distinct field by field, so a
column swapped in a query fails a contract; it moves the four existing contracts over a database to the same drawn
values, and every contract to ports received as fixtures, without the pairs' `<Thing>Ports` wrapper. Writing the
promises down shows two searches that do not do what their ports say, and behaviours the webui and the download loop
rely on that no port states: the lot fixes the first and writes the second into the ports. The package's two other
ports, `SqlExecutor` (the SQL console) and `CatalogCopier` (`merge`), stay out: each promise names SQLite itself, a SQL
text or a catalog file, so no other implementation can exist.

## 2. What the operator will see

- **The search of the webui's files and sources pages is literal, and ignores case and accents**: `%` and `_` typed in
  it match only themselves, where today they are wildcards (`a_b` finds `axb.avi`); `ecole` and `ÉCOLE` find `école`,
  where today only the case of ASCII letters is ignored (D5).
- Nothing else: no schema change, no new key, no other page changes. `git diff --stat origin/main...<top> --
  '*/migrations/*' deploy/ '*/webui/templates/*'` prints nothing.

## 3. Decisions

- **D1. A contract for each of the eight ports above, and the four existing contracts over a database
  (`TrackedDownloadStoreContract`, `BackoffStateStoreContract`, `NodeIdStoreContract`,
  `PolicyFingerprintStoreContract`) moved to drawn values.** *A contract states once what any implementation must do,
  where an adapter test covers one implementation's branches (Appendix B of the lot "Rows read by column name"); the
  swap above shows hand-picked values miss what a contract must catch. The four existing ones move so that one rule
  holds for every contract over a database, the lot drawing three of their values anyway for `NodeStateReader`
  (operator, 2026-11-01); the contracts over memory or a file (`RunStateStoreContract`, `StatusReadingStoreContract`,
  `NodeMetricStoreContract`, `AmuleConfStoreContract`, `DockerfileStoreContract`) keep their values, since a column
  swapped in a query is a database's failure.*
- **D2. A contract seeds only through the Writers**, a reader's through those of the state it reads (Appendix A).
  *A raw SQL seed holds only for SQLite (Rainsberger, contract and collaboration tests); kept from 2026-10-29.*
- **D3. A contract receives each port it uses through an abstract fixture of its own**: `writer` and `reader` for a
  pair's ports, `reader` for a reader-only port, and each Writer it seeds through named after its port in snake case
  (`observation_writer`); each test's parameters are typed by the ports. The `<Thing>Ports` of the nine existing pair
  contracts (seven in the crawler, `AmuleConfStoreContract`, `DockerfileStoreContract`) give way to the same fixtures.
  *A wrapper is avoidable here: typed parameters have mypy check every call a test makes on a port, as `<Thing>Ports`
  does. What `<Thing>Ports` adds is a check of the subclass's wiring, which `pytest.fixture` hides from mypy; but an
  object of the wrong port fails, at its first run, every test that calls it, and a reader on another database fails
  every test that reads what it wrote, which mypy cannot see either way (operator, 2026-11-01). Revises the pairs'
  `<Thing>Ports` of 2026-10-30 (`c9f3fd4a`), which replaced a `Protocol` copying the ports' signatures, and keeps the
  "one abstract fixture per port it uses" of 2026-10-29.*
- **D4. The wide values are drawn, the narrow ones written by the test.** A draw fills every text, integer and instant
  of a value, distinct from the value's other fields of the same type by construction; the test writes only what would
  pick a Python branch (a value present or absent, a tier, a role, a state). One `random.Random` per test, seeded from
  its node id, so a test's values are the same on every run whatever the order or the selection. *Catching a swap
  needs two columns with distinct values, which a draw guarantees and a hand-picked pair may not; Hypothesis's hundred
  examples and shrinking add nothing here, for a new dependency and a much longer mutation run (operator,
  2026-10-30); distinct by construction, since a seed giving two equal values would weaken a test silently; narrow
  values written so that no draw picks a branch, and renaming a test or editing a draw cannot move a branch's
  coverage (operator, 2026-11-01).* The values a draw avoids: Appendix C.
- **D5. The search is literal, and ignores case and accents**: `CatalogFileReader` and `SourceReader` find a text as
  typed, `%`, `_` and every other character included, as a substring of a filename or a name, or the start of a user
  hash, both sides compared casefolded and stripped of their accents. *`CatalogFileReader` promises a filename that
  "contains" the text, and `SourceReader`'s "matches" leaves wildcards unstated: neither port promises `LIKE`'s
  wildcards, which every implementation would otherwise have to imitate, and one rule serves the webui's two search
  boxes. Case and accents ignored because the names sought are French and a visitor often types without accents: on
  the node's catalog, 958 of 3,615 distinct filenames hold a non-ASCII letter that has a case, mostly mojibake (`Ã`,
  `Â`) but real accents too (`é` in 69), where `_` is in 74 (Appendix E). The cost stays small at the node's scale
  (Appendix E). Chosen over `LIKE`'s wildcards described in the ports, over the case of ASCII letters alone, and over
  the case alone without the accents (operator, 2026-11-01, after the spec review refuted the lead's claim that a
  function of our own was slower on a large catalog).*
- **D6. A behaviour a production consumer relies on enters its port's docstring, and its contract tests it**
  (Appendix B). A consumer relies on a behaviour when another implementation's different choice would make its outcome
  wrong: a value it shows or acts on, the order of a list it shows, an order a port already states, which is then
  stated whole (its ties, where an absent value falls). Which of two rows of the same instant wins and a duplicate row
  stored once stay unstated and tested by their adapter: no consumer's outcome is wrong for another choice.
  *`AGENTS.md`, "The port is the reference": a port's docstring is its promise; promising more than a consumer needs
  would bind every implementation for nothing.*
- **D7. An adapter test a contract restates is deleted; the rest stays** (Appendix D): what no port returns (the
  column a value is written to, a reading's `software` and `raw_metadata`), what no Writer can produce (a `files` row
  without an observation), rollbacks, migrations, error mapping, the tie rules of D6. *A test that a contract restates
  checks nothing more (D10 of `agents/specs/2026-10-25-fake-contract-tests.md`); a write swap undone by a read swap
  passes every round trip, so the column checks stay.*
- **D8. The doubles of these ports are stubs or spies, exempted by name** in `test_contract_subclasses.py`, each with
  its reason (Appendix A). *A stub promises only the answer its test gives it, so it cannot pass a contract; kept from
  2026-10-29.*

The operator decided D1 to D8 on 2026-10-29, 2026-10-30 and 2026-11-01, as each states.

## 4. Conventions

Durable conventions, written into `AGENTS.md`'s Hard rules (the contracts bullet) and `docs/contributing/testing.md`
by the block that first applies them.

- **C1** (D3, block 10): a contract receives each port it uses through an abstract fixture of its own, `writer` and
  `reader` for a pair's ports, `reader` for a reader-only port, each Writer it seeds through named after its port in
  snake case, each test's parameters typed by the ports. It replaces `AGENTS.md`'s `<Thing>Ports` sentence.
- **C2** (D4, block 20): a contract over a database draws its wide values from a `randomness` fixture, a
  `random.Random` seeded from the test's node id, through a `draw_<value>` per value a Writer takes, in
  `tests/support/`; the test writes only the narrow values.

"Draw", "wide value" and "narrow value" get no glossary line: the glossary takes only the terms the operator asks for.

## 5. Acceptance

1. Each of the eight contracts has its SQLite subclass, `Test<Implementation>`, in the implementation's own test
   module, and `test_contract_subclasses.py` passes with the eight doubles of Appendix A exempted; deleting one
   subclass makes it fail naming the implementation. `pytest --collect-only -q --no-cov` lists a test under each of
   the twelve SQLite subclasses.
2. Each swap of Appendix E, applied alone to the query it names, fails at least one contract test; the block's report
   quotes the failing line. On `main`, the files list's swap passes the crawler's whole unit suite (Appendix E).
3. Each promise of Appendix B is stated in its port's docstring and tested by its contract: with the implementation
   mutated as the row names (an `ORDER BY` dropped, a tier counted 0), its contract test fails. The closing block's
   handoff holds one row per promise: the port line, the contract test, the failing line.
4. Through each search of `CatalogFileReader` and `SourceReader` (filename, name, hash prefix): a text holding `%`, `_`
   or `\` finds only a name holding it as typed; `ÉCOLE` and `ecole` find `école`; `KERORO` finds `Keroro`. The `%`,
   `_`, `ÉCOLE` and `ecole` cases fail first on `main`; the ASCII case and the `\` one pass there (`LIKE` without
   `ESCAPE` takes `\` as typed), the latter guarding against a fix built on `ESCAPE`.
5. The draws' own test: over 1000 seeds, the same-type fields of each drawn value differ, and two `random.Random` of the
   same seed give the same value. `git grep -nE 'datetime\(|timedelta\(|" \* 32|TargetId\("[^"]|_bytes=[0-9]'` over the
   twelve contract modules over a database prints nothing; on `main` it prints the constants of the four existing ones.
6. Each block's report maps every adapter test it deletes to the contract test that restates it.
7. No `<Thing>Ports` is left: `git grep -nE 'class [A-Z][A-Za-z]*Ports\b' -- packages` prints nothing, where on
   `main` it prints the nine pair contracts' dataclasses (9 lines; with `-- 'packages/*/tests'` and `-E`, git grep
   prints nothing even on `main`, so the pathspec stays `packages`).
8. `uv run poe check` passes at each block's tip: the per-package 100 %, each module covered by its own tests.

## 6. Blocks

Estimates by `round-trip-estimates` (Sonnet), 2026-11-01, deletions measured on pruned copies (about 5 %), contracts
modelled on `tracked_download_store_contract.py` (about 20 %); the bound is checked after committing. The contract of
a port comes before the contracts that seed through its Writer, and a contract before the deletion of the adapter tests
it restates, which stay green until then. A block deleting tests deletes only those the contracts in the tree at its tip
restate, its report mapping each to its contract test (acceptance 6).

| # | Branch | Holds | Lines (contract part), files |
|---|---|---|---|
| 10 | `refactor/contract-port-fixtures` | the spec, the nine pair contracts' `<Thing>Ports` replaced by fixtures (D3), C1; mechanical | about 490, 30 |
| 20 | `test/observation-store-contract` | `randomness`, the draws of observations, `ObservationStoreContract`, C2, the tests it restates | 629 (411, 350 to 480), 14 |
| 30 | `test/decision-store-contract` | `DecisionStoreContract`, the draws of decisions, the tests it restates | 553 (317), 8 |
| 40 | `test/source-point-store-contract` | `SourcePointStoreContract`, the draws of source points, the tests it restates | 439 (329), 7 |
| 50 | `test/scan-and-coverage-reader-contracts` | `CatalogScanReaderContract`, `CoverageReaderContract`, the tests they restate | 449 (278), 7 |
| 60 | `fix/file-search` | `CatalogFileReaderContract`: the listing's filters, D5 for files, the tests it restates | 554 (386), 5 |
| 70 | `test/file-listing-and-history-contract` | `CatalogFileReaderContract`: the listing's order and page, a file's history, the tests it restates | 546 (325), 2 |
| 80 | `test/file-count-contract` | `CatalogFileReaderContract`: the counts, the tests it restates | 355 (195), 3 |
| 90 | `fix/source-search` | `SourceReaderContract`: the sources lists, D5 for sources, the tests it restates | 356 (272), 5 |
| 100 | `test/sharing-period-contract` | `SourceReaderContract`: the sharing periods, the tests it restates | 452 (250), 3 |
| 110 | `test/source-history-contract` | `SourceReaderContract`: the source and name histories, the tests it restates, `catalog_seeds.py` | 733 (375), 3 |
| 120 | `test/drawn-values-in-local-contracts` | the draws of `local.db`'s values, the four existing contracts on them | 315, about 10 |
| 130 | `test/node-state-reader-contract` | `NodeStateReaderContract`, the tests it restates | 457 (277), 6 |
| 140 | `docs/wrap-round-trip-contracts` | closing, section 8's documents | 12, 2 |

Two size exemptions, granted by the operator on 2026-11-01:

- **Block 10 is mechanical**: one change repeated over every pair contract and its subclasses (each
  `<thing>_ports.writer` becomes `writer`, each `<Thing>Ports(...)` two fixtures); splitting it would leave two forms of
  contract on `main` between its halves. Its size, in place of a Sonnet agent's estimate, is that of the commit it
  reverts, `c9f3fd4a` (487 changed lines over 29 files, by `agents/workflow.md`'s command; the spec review): 9 contract
  modules and 19 subclass modules in the crawler, `amule` and `amule_bump`, plus `AGENTS.md` and
  `docs/contributing/testing.md`.
- **A block may pass 500 lines when the lines past it are adapter tests deleted**, each mapped to the contract test
  that restates it (acceptance 6), which the review reads in place of every deleted line, as the pruning blocks of
  "Test quality" do (D15 of `agents/specs/2026-10-14-gate-tooling-and-test-quality.md`); the rest of the block stays
  under 500 lines and 20 files. So each block holds a contract, or a group of a large reader's methods, with the tests
  it restates, and no block only deletes.

## 7. Limits and scope

### Accepted limits

- **A write swap undone by a read swap passes every round trip**: the adapter tests that read the stored columns keep
  it (D7).
- **A reading's `software` and `raw_metadata` are returned by no port**: only their adapter test checks them.
- **`Network` has one member**, so a swap between two `Network` columns stays invisible until stage 5 adds one.
- **Two draws, unlike two fields of one value, differ by width alone**, and so do two fields of different types stored
  as `INTEGER` (an instant's micros and a received bytes count, a backoff's attempts and its start): a collision has a
  negligible chance, and a seed that gave one would give it on every run, never flake.
- **A working fake wired into an SQLite subclass would pass every contract test**: no check reads what a fixture
  builds, under `<Thing>Ports` as under plain fixtures (D3); the subclass's name and module say what it must build.
- **The search does not find a name whose encoding is broken** (`Ã©cole` for `école`): the fold strips accents from
  well-encoded letters only (D5).
- **A backoff's delay of 2\*\*33 seconds (about 272 years) or more loses its microseconds**, stored as `REAL` seconds:
  draws stay below 10\*\*9 seconds, and a real delay is minutes long (Appendix C).

### Backlog

The closing block deletes "Round-trip contracts". No entry is added.

### Adjacent backlog items

- "Test quality": the next of the debt; its unique-coverage rule (every test covers a branch no other test of its module
  covers) judges redundant 21 of the 22 contract tests of the four existing SQLite subclasses (Appendix E), so its
  spec decides how a contract's tests count; whether it comes before or after the v5 tag is the operator's call then.
  It stays open.
- "A generic way to write the tests' stubs and spies": would replace the eight doubles D8 exempts; it stays open.
- "Mutation testing in the gate": would have found the files list's swap mechanically; it stays open.
- "Contract tests for the fakes of outside systems": outside systems, not our stores; it stays open.
- "Multi network", stage 5: a second `Network` makes its swaps visible to these contracts; it stays open.
- "aMule 3.2.0 pinned", "The Grype scan back on p2pwatch": with this lot, the conditions of the v5 tag; they stay open.
- "`merge` refuses a source whose schema is not the node's", "Adopt ty", "A rule test naming no rule fails the gate",
  "Sort the files view by first seen", "The webui in the visitor's time zone": unrelated; they stay open.

## 8. Documents

- `AGENTS.md`'s Hard rules, the contracts bullet: C1 (block 10), C2 (block 20).
- `docs/contributing/testing.md`, the contracts: the ports they receive as fixtures (block 10), their drawn values
  (block 20).
- `docs/migration-4x.md`: the literal search (block 140), as it lists what v5 changes for the operator.
- The closing block's handoff, with acceptance 3's table.

## Appendix A. The contracts

Paths under `packages/crawler/`. Contracts in `tests/contracts/application/ports/driven/`, at the mirror of their port.

| Contract | Fixtures (D3) | SQLite subclass | Doubles exempted (D8) |
|---|---|---|---|
| `ObservationStoreContract` | `writer`, `reader` | `TestSqliteObservationStore` | `FakeObservationReader`, stub |
| `DecisionStoreContract` | `observation_writer`, `writer`, `reader` | `TestSqliteDecisionStore` | `FakeDecisionReader`, stub; `FakeShutdownDuringCycleDecisionReader`, stub that requests the shutdown |
| `SourcePointStoreContract` | `observation_writer`, `writer`, `reader` | `TestSqliteSourcePointStore` | `FakeSourcePointStore`, stub and spy |
| `CatalogScanReaderContract` | `observation_writer`, `reader` | `TestSqliteCatalogScanReader` | none |
| `CoverageReaderContract` | `observation_writer`, `decision_writer`, `reader` | `TestSqliteCoverageReader` | `FakeCoverageReader`, stub |
| `CatalogFileReaderContract` | `observation_writer`, `decision_writer`, `reader` | `TestSqliteCatalogFileReader` | `FakeCatalogFileReader`, stub and spy |
| `SourceReaderContract` | `observation_writer`, `source_point_writer`, `reader` | `TestSqliteSourceReader` | `FakeSourceReader`, stub and spy |
| `NodeStateReaderContract` | `node_id_writer`, `tracked_download_writer`, `backoff_state_writer`, `reader` | `TestSqliteNodeStateReader` | `FakeNodeStateReader`, stub |

- **The seeding Writers share one database with the reader**: the subclass builds them on one catalog (or one
  `local.db` for `NodeStateReader`); the foreign keys to `files` make every catalog contract but `CatalogScanReader`'s
  seed through `ObservationWriter` too.
- **The draws**: a `draw_<value>` per value a Writer takes, at the mirror of the module defining its type
  (`tests/support/domain/observation.py` for `ReportedFile` and `FileObservation`, `.../file_target_decision.py` for
  `DatedDecision`, `.../source.py` for `SourcePoint`), the draws of a text, a quantity and an instant in
  `tests/support/draws.py`; keyword arguments for the narrow values and for what a test relates (the same file, a later
  instant). Distinct without a retry loop: a branch that only a colliding seed takes would fail the 100 % of
  `tests/support`. The `randomness` fixture lives in `tests/conftest.py`: `random.Random(request.node.nodeid)`, a `str`
  seed hashed by SHA-512, the same in every process whatever `PYTHONHASHSEED`.
- **The search (D5)** compares with `instr(fold_for_search(<column>), fold_for_search(:search_text))`, `> 0` for a
  substring and `= 1` for a hash prefix, so no character of the text is a wildcard and nothing needs escaping.
  `fold_for_search` is a Python function of the adapter, the text casefolded, decomposed (NFD) and stripped of its
  combining marks (`None` for `None`), registered with `deterministic=True` by `register_sql_functions`, which
  `SqliteDatabaseOpener` runs on every connection it opens, the readers' included. Each block checks with
  `EXPLAIN QUERY PLAN` that its search keeps its plan (a scan today, since the default `LIKE` uses no index on a
  `BINARY` column).
- **What a contract cannot seed** stays in an adapter test: a `files` row without an observation (behind
  `CatalogEntry.latest_observation is None`, the null-first sort, `CatalogScanReader.read_file_count`), a file with
  sharing periods and no observation (`best_filename_by_file`'s `None`), and one timeline test of
  `observation_read.py`, which its own tests must run. `tests/support/adapters/driven/persistence_sqlite/catalog_seeds.py`
  goes with the last restated test that uses it.

## Appendix B. The promises written into the ports (D6)

From `round-trip-survey` (2026-11-01); each consumer is a production path that relies on the behaviour. Paths under
`packages/crawler/src/p2pwatch/`.

| Port | Promise | Consumer | Mutation that must fail its contract |
|---|---|---|---|
| `ObservationReader.read_best_observation` | `None` for a file never observed | `application/steps/download_labeler.py:31` | the missing row read without its `None` check |
| `DecisionReader.read_download_candidates` | a file's candidates in target id order (the decider's queueing order, by file, is arbitrary and stays unstated) | `application/steps/download_labeler.py:36` lists a file's targets in this order | `target_id DESC` |
| `CatalogFileReader.read_file_count_by_tier` | a tier no file holds is absent, not 0 | `adapters/driving/webui/app.py:541` | every tier counted, 0 included |
| `CatalogFileReader`, `CatalogEntry.size_bytes`, `FileHistory.size_bytes` | the size the file was first observed with | `app.py:218`, `app.py:1111`, the size sort | the latest observation's size |
| `CatalogFileReader`, `CoverageReader` | the old retraction with an empty target id, which v4 catalogs hold, left out | the webui's file and targets pages | the `target_id <> ''` filter dropped |
| `CatalogFileReader`, `SourceReader` | D5's search, literal, case and accents ignored; for sources, a substring of any name the source carried | `app.py:844`, `app.py:934` | the `LIKE` of `main`; the fold without its accents stripped |
| `NodeStateReader` | its stated orders whole: a client's whole-client backoff before its channels; downloads of the same `queued_at` by native id | `app.py:697`, `app.py:681` | `channel DESC`; `native_id DESC` |
| `SourceReader` | a sharing period is cut on a gap past `window.gap`, a drop of the session's received bytes or a change of variant; its `received_bytes` is the growth of the session counter while sending | `application/use_cases/describe_file.py:63` and the webui's source pages | each rule dropped alone (four mutations); the growth read as the latest count |
| `SourcePointReader.read_latest_point` | `since` included, `before` excluded | `application/steps/source_watcher.py` | `>` for `>= :since`; `<=` for `< :before` |

Adjacent, class 1, in block 130: `SqliteTrackedDownloadStore.set_state`'s docstring says `failure_reason` is cleared by
"any other call", where only another `set_state` or `set_completed` clears it (`set_seen` leaves it).

## Appendix C. The values a draw avoids (D4)

- From Appendix D of the lot "Values checked at the boundary": a text that is not valid UTF-8 (a surrogate, paired or
  not); an integer outside [-2\*\*63, 2\*\*63), and a negative one where the domain or a `CHECK` refuses it (sizes,
  counts, durations, bitrates, received bytes); a control character in a target id or a rule name; `attempts < 1` and
  a negative delay; a non-canonical native id.
- An empty target id: no production path writes one (a target id is always `models.py:46`'s `"062A"` form), and the
  readers read it three ways (`round-trip-survey`, 1.2); the old retraction that holds one is seeded explicitly
  (Appendix B).
- A search text drawn to miss that matches a name once both are casefolded and stripped of their accents (D5).
- A delay of 10\*\*9 seconds or more, a margin below 2\*\*33 s, from which a delay round-tripped through `REAL` seconds
  loses its microseconds (the spec review: 0 of 5000 lose them in [10\*\*9, 2 \* 10\*\*9) and 0 of 5000 in
  [2 \* 10\*\*9, 2\*\*33), 2352 of 5000 in [2\*\*33, 10\*\*10)).
- Two instants of one value are distinct (a sharing period's first and last reading), and the media fields are both
  present when a test reads them, or a swap between them stays hidden.

## Appendix D. Size (`round-trip-survey`, 2026-11-01)

Of the 155 test functions of the twelve SQLite test files the eight ports' adapters own, 106 are restated by a contract
and 49 stay. Re-counted by each block on its tree.

| SQLite test file (`tests/adapters/driven/persistence_sqlite/`) | functions | restated | stay |
|---|---:|---:|---:|
| `test_sqlite_observation_store.py` | 10 | 0 | 10 |
| `test_sqlite_observation_store_reads.py` | 7 | 7 | 0 |
| `test_observation_read.py` | 14 | 7 | 7 |
| `test_sqlite_decision_store.py` | 15 | 8 | 7 |
| `test_sqlite_decision_store_latest_decisions.py` | 6 | 6 | 0 |
| `test_sqlite_source_point_store.py` | 9 | 6 | 3 |
| `test_sqlite_source_point_store_writer.py` | 8 | 0 | 8 |
| `test_sqlite_catalog_file_reader.py` | 47 | 38 | 9 |
| `test_sqlite_catalog_scan_reader.py` | 5 | 3 | 2 |
| `test_sqlite_coverage_reader.py` | 9 | 8 | 1 |
| `test_sqlite_node_state_reader.py` | 5 | 5 | 0 |
| `test_sqlite_source_reader.py` | 20 | 18 | 2 |

## Appendix E. Facts, 2026-11-01, on `main` at `49ddd7fe`

- **The files list's swap passes**: `obs.bitrate_kbps AS duration_seconds` and `obs.duration_seconds AS bitrate_kbps` in
  `_SQL_LIST_FILES_BASE` (`sqlite_catalog_file_reader.py:126-127`), in a throwaway worktree, `__pycache__` cleared, the
  loaded module checked as swapped: `uv run pytest --no-cov -q -p no:cacheprovider` from `packages/crawler`, 2020
  passed, exit 0. The only list test with media fields sets both to `None`. Control: the same swap in
  `observation_read._FROM_OBSERVATIONS` fails `test_file_history_observations_include_media_fields_present`.
- **The swaps acceptance 2 applies**, one per query a contract reads, each alone:

  | Query | Columns swapped |
  |---|---|
  | `observation_read.py`, the latest observation | `size_bytes` and `source_count` |
  | `observation_read.py`, the timeline | `filename` and `keyword` |
  | `_SQL_LIST_FILES_BASE` | `duration_seconds` and `bitrate_kbps`; `obs.size_bytes` and `f.size_bytes`; `target_ids` and `rule_names` |
  | `sqlite_catalog_file_reader.py`, a file's decisions | `target_id` and `rule_name` |
  | `sqlite_catalog_file_reader.py`, the matched and total counts | `matched` and `total` |
  | `sqlite_decision_store.py`, the latest decisions; the download candidates | `target_id` and `rule_name`; `native_id` and `target_id` |
  | `sqlite_source_point_store.py`, the latest point | `observed_at_micros` and `session_received_bytes` |
  | `sqlite_source_point_store.py`, the earlier points (`_EARLIER_POINTS`) | `observed_at_micros` and `session_received_bytes` |
  | `sqlite_source_reader.py`, the periods; the known sources and namings | `file_native_id` and `native_id`, `first_seen_at_micros` and `last_seen_at_micros`; `latest_seen_at_micros` and `file_count` |
  | `sqlite_node_state_reader.py` | `queued_at_micros` and `latest_progress_at_micros`; `native_id` and `target_id`; `client_name` and `channel`; `attempts` and `started_at_micros` |
  | `sqlite_backoff_state_store._SELECT` (block 120) | `client_name` and `channel`; `attempts` and `started_at_micros` |

  The other three existing stores' reads return no two columns a swap would leave quiet: one column each for the node
  id and the policy fingerprint, and `network` beside `native_id` for the tracked downloads, which `Network` refuses.

- **The node's filenames** (`/home/geoffrey/Projets/mulewatch/data/catalog.db`, `user_version` 5, opened `mode=ro`,
  the node stopped): `SELECT DISTINCT filename FROM file_observations WHERE filename IS NOT NULL` gives 3,615 names;
  74 hold `_`, 1 holds `%`, 1,004 a non-ASCII letter, 958 one that has a case; the most frequent: `Ã` 451, `Â` 352,
  `ì` 153, `é` 69, `ó` 59.
- **The fold's cost**, isolated (`fold_bench.py` in the lead's scratchpad, 300,000 random names of 20 to 80 letters
  with accents, in memory, median of 5): `instr(lower())` 50 ms, a registered `casefold` 180 ms, casefold and accents
  stripped 1,004 ms, so about 7 ms for the node's 2,162 files by proportion (not measured on them). In the files
  list's real query over 50,000 files, the spec review measured `LIKE` 444 ms, `instr(lower())` 455 ms, a registered `casefold` 458 ms and no search 452 ms:
  the latest observation's CTE dominates.
- **`LIKE`** (`round-trip-survey`, sqlite3): `'axb.avi' LIKE '%a_b%'` is 1, `'Keroro 062A.avi' LIKE '%KERORO%'` is 1,
  `'école' LIKE '%ÉCOLE%'` is 0. The webui passes the visitor's text stripped only (`app.py:844`, `app.py:934`).
- **Unique coverage of the existing contract tests**: the four SQLite test modules of the contracted stores, run with
  `--cov=p2pwatch --cov-branch --cov-context=test`, each test function's arcs of its module compared with those of the
  module's other tests: 1 of 22 contract tests covers an arc no other covers (`SqliteBackoffStateStore`'s three reads
  share the same 36 arcs); 42 passed, the number the four modules hold.
- **Pitfall for the probes** (handoff of the lot "Every catalog table STRICT"): pytest can reuse a stale `.pyc` for a
  module changed to the same size within the same second; clear `__pycache__` before trusting a swap that passes.

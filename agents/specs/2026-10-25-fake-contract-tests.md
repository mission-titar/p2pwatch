# Contract tests for the fakes

- Date: 2026-10-25. Status: approved by the operator, 2026-10-25, after review (`contract-spec-review`).
- Tier: Spec. Origin: the backlog entry "Contract tests for the fakes", the Discuss of 2026-10-25.
- Size: 13 blocks with the closing one, none expected past a bound.
- Measured on `main` at `84d6c0fe`. Paths: `C` is `packages/crawler/`, `A` is `packages/amule/`, `B` is
  `packages/amule_bump/`.

## In short

- A contract is a port's promise, written once as an abstract pytest suite and run by every implementation of the port:
  the real adapter and each fake.
- The port is the reference, never the real adapter. Its docstring is the promise and the contract tests all of it; a
  behaviour the port leaves unstated enters the docstring when a production consumer relies on it.
- In scope: the fakes that hold state (six crawler stores, amule's and amule_bump's stores), the clocks and the waker.
  Twelve suites, 28 subclasses.
- A structure test refuses an implementation of a contracted port without its subclass, a subclass left abstract, and a stale
  exemption.
- Six fakes are fixed; the tests that a contract restates are pruned.

## What an operator sees change

Nothing. The lot touches tests and test support, the docstrings of the eight port files listed in acceptance 4, the
three packages' `pyproject.toml` (`tests_without_unit`), `AGENTS.md` and `docs/contributing/testing.md`; no code in
`src` and no image change. (Corrected: the closing block also rewords seven `src` docstrings that used "contract" in
another sense (acceptance 4), and the three `pyproject.toml`'s coverage comment.)

## Conventions

Each goes into `AGENTS.md` in the block that first applies it.

- **C1. A contract per contracted port, or per Writer/Reader pair.** `<Port>Contract`, or `<Thing>StoreContract` for a
  pair, an ABC in `tests/contracts/application/ports/driven/<snake case>_contract.py`, at the mirror of the port, whose
  abstract fixture builds the implementation under test and whose tests state the port's docstrings. `tests/contracts`
  holds no `test_*.py`; like `tests/fakes` and `tests/support`, it is measured at 100 % and left out of
  `_unit-coverage-check`. Each package's `tests/conftest.py` registers `tests.contracts` for pytest's assertion
  rewriting, since pytest rewrites only test modules, conftests and plugins, and a contract's failing `assert` would
  otherwise print a bare `AssertionError`. Hard rules, block 20. (Corrected: a pair's contract types its fixture with
  a `Protocol` of the pair, `<Thing>Store`, in the contract's module, since an implementation shares no nominal base
  with the pair; applied from block 20, written into `AGENTS.md` and `testing.md` by the closing block.)
- **C2. A subclass per implementation, `Test<Implementation>`**, in the implementation's own test module: a real adapter's
  test module, or for a fake `tests/fakes/<path of the fake>/test_<fake module>.py`, listed in `tests_without_unit`.
  Hard rules, block 20. (Corrected: nothing checked the module until the closing block's structure test, which expects
  `tests/a/test_b*.py` for `src/<pkg>/a/b.py` and `tests/fakes/a/test_b.py` for `tests/fakes/a/b.py`.)
- **C3. The port is the reference.** A port's docstring is its promise and its contract tests all of it; a behaviour
  the port leaves unstated enters the docstring when a production consumer relies on it; a double's docstring describes
  the double against its port, never against another implementation. Hard rules, block 20.
- **C4. Glossary**: `fake`, `stub`, `spy`, `contract` (a port's promise as a test suite). Naming,
  block 20, which renames the amuleapi adapter's "error contract" (`AGENTS.md`'s subsystem table) its "error mapping".

## Decisions

Details per decision: appendix A.

- **D1. Scope: the doubles that hold state readable back through their port.** The crawler's stores of `BackoffState`,
  `NodeId`, `PolicyFingerprint`, `StatusReading`, `TrackedDownload` and `RunState`; amule's `AmuleConf` store and
  `MonotonicClock`; amule_bump's `Dockerfile` store; the crawler's `MonotonicClock`, `WallClock` and `Waker`. Why: a
  contract binds a working implementation (Meszaros's Fake Object); a stub promises only the answer its test gives it,
  so no shared suite can hold of it and of the real adapter.
- **D2. Out of scope, each for its reason.** Stubs and spies, `FakeSourcePointStore` among them (its reads return what
  its constructor was given, never what `record_points` wrote): the backlog's decoy lot replaces them. The sabotaged
  doubles `FakeBlockingMonotonicClock` and `FakeNoSetStateTrackedDownloadStore`: they break their port on purpose, so
  the structure test exempts them by name, each with its reason. Outside systems: their real side is an outside system,
  run only under the integration markers (the backlog's entry). `FakeImmediateEventLoop` and `FakeRecordingEventLoop`:
  they replace an asyncio loop, no port. The `Decision` and `Observation` stores: one implementation each, nothing to
  hold to a common promise.
- **D3. The port is the reference (C3).** Why: the fake and the real adapter both implement the port, so a difference
  between them matters only when one breaks the port. What a test cannot express (a change applied on the next loop
  tick, a file's owner and mode) stays in the port's docstring, checked in review.
- **D4. What a port promises is its docstring, all of it tested; a silence is judged by one criterion: does a
  production consumer rely on it** (appendix A, table A1). Relied on, it enters the docstring; otherwise it stays
  unspecified and untested. A promise already stated stays and is tested, relied on or not (`record_queued` keeping an
  already tracked file's row, the refusal of a second node id). Why: a consumer relying on an unstated behaviour has no
  guarantee; stating what nobody relies on freezes detail in the port; and a stated promise is an invariant someone
  chose, which a later implementation must not drop unseen.
- **D5. A suite is an abstract base class, its subclasses in the implementations' own test modules** (Meszaros's Abstract
  Test Case). Why: the real adapter's subclass sits in the adapter's own test module, so the mirror rule and
  `_unit-coverage-check` credit the adapter with no exception (`_unit-coverage-check` selects contexts by the test
  file, and an inherited test's node id carries the subclass's file); a parametrized fixture would put every implementation
  in one module that mirrors none.
- **D16. The suites live in `tests/contracts/` (C1).** Why: a suite is neither a double nor a helper but the port's
  tests, which its subclasses run; `tests/support/` holds what is no double (`AGENTS.md`), so a directory of their own names
  their role, as `tests/fakes/` names the doubles' (the operator, 2026-10-25). A `test_*.py` per port would have its
  subclasses import a test module and be listed in `tests_without_unit`, a port having no code to cover.
- **D6. One suite per Writer/Reader pair, named after its store.** Why: a Writer's promise is observable only through its
  Reader. It follows lot "test tooling and layout"'s pairing (its D5: splitting a pair would make every test build a
  writer, a reader and a shared state) and revises that D5's "a contract test runs per port".
- **D7. A subclass is named `Test<Implementation>` (C2).** Why: the structure test links a subclass to the class it covers by
  name, and pytest's report then names the implementation; reading the fixture's return annotation would mean unfolding
  `Iterator[...]` and its variants, and two subclasses could cover one class unseen.
- **D8. The structure test reads the AST**, one test for every package, `C/tests/test_contract_subclasses.py`, on
  `test_fake_files.py`'s machinery moved to `C/tests/support/port_implementations.py`. A suite covers, in its own package,
  `<Thing>Reader` and `<Thing>Writer` when named `<Thing>StoreContract`, `<Port>` when named `<Port>Contract`. For each
  suite, every class implementing its ports in the package's `src` or `tests/fakes`, transitively, has a subclass
  `Test<Implementation>` inheriting the suite, or an exemption; every subclass defines each abstract fixture of its suite;
  every exemption names an implementation of a contracted port. Why: the machinery already resolves bases across files
  and packages, where discovery at run time would import every module and need declarations in three packages; pytest
  9.1.1 silently skips a test class left abstract (appendix B), so a subclass that forgets its fixture would run nothing; a
  stale exemption is refused as `tests_without_unit` refuses a stale listing. Accepted limit: `test_fake_files.py`'s
  reach (a base written `module.Port`, a relative import, a re-export), which no file of the tree uses (appendix B).
  (Corrected: four checks from block 20, the fourth refusing a contract whose name matches no port of its package,
  which would otherwise check nothing; a fifth from the closing block, each subclass in its implementation's own test
  module (C2). Each store contract also declares a `Protocol` of its pair to type its fixture (C1).)
- **D9. Six fakes are fixed**, each to pass a promise its contract tests: `FakeNodeIdStore` refuses a second id and
  `FakeTrackedDownloadStore` keeps an already tracked file's row, both promises their ports state (D4);
  `FakeStatusReadingStore` is built with its client names, a promise relied on (A1); `FakeLoopMonotonicClock` and
  `FakeLoopWallClock` receive their loop so that `now()` works from any thread, relied on (A1); `FakeAmuleConfStore`
  gets a read error, the knob its contract needs to reach the `OSError` its port states. No test depends on a behaviour
  these fixes remove (appendix B).
- **D10. A test that a contract restates is deleted**: a real adapter's (the rest stays: SQL rows, migrations, rollbacks,
  threads, file modes), and those of `C/tests/application/test_fakes.py` on the contracted fakes (`FakeTime`'s clocks,
  lines 22 and 33). Why: covering twice brings nothing (the operator, 2026-10-14). (Corrected: no contract restates
  `test_fakes.py`'s two tests, "a monotonic sleep moves the wall clock" and "`step_wall` leaves the monotonic clock",
  which are `FakeTime`'s own behaviour; their deletion stands because the consumers' tests catch both breaks, 10 and 2
  failures under the holistic review's mutations. And block 80 pruned `AsyncioMonotonicClock`'s bounded read, which
  no contract restates since it names the clock read; the closing block restores it.)
- **D11. A fake keeps its fault knobs and spy attributes; its contract runs on its default configuration, but for a
  knob that reaches a failure the port states** (`FakeAmuleConfStore`'s read error). Why: the knobs test our failure
  handling, and a decoy mock cannot make a working store fail on its third write.
- **D12. The clocks promise to the microsecond.** `sleep(d)` then `now()` is at least `d` later, less one microsecond.
  Why: asyncio may fire a timer up to its clock's resolution early and `FakeLoopMonotonicClock` rounds to the
  microsecond, while every consumer re-checks its deadline after waking (A1).
- **D13. The real clocks' contracts sleep for real, 10 ms per sleep.** Why: a real sleep is observable no other way, and
  the gate pays a few tens of milliseconds.
- **D14. A fake's subclass lives beside the fake (C2).** Why: like a real adapter's subclass in the adapter's test module, it
  sits at the mirror of what it covers, where a reader of the fake finds it; `test_fakes.py` sits under
  `tests/application/`, which mirrors nothing it tests. Block 20 amends the two sentences this makes false
  (`AGENTS.md`: `tests/fakes` holds no `test_*.py`; `docs/contributing/testing.md`: « Aucun fichier nommé `test_*.py`
  n'y vit »), and `test_fake_files.py` skips the `test_*.py` files of `tests/fakes`, which hold subclasses, not doubles.
  (Corrected: the skip and both sentences landed in block 10, whose move of `FakeAmuleApiServer`'s tests made the check
  fail and the sentences false. The skip also hid a port's implementation written in such a file from every structure
  check; the closing block has the stray-class check of `test_fake_files.py` treat a `test_*.py` of `tests/fakes` as
  outside the fakes.)
- **D15. C3 holds of every double from block 20.** The docstrings that compare a double with another implementation are
  rewritten, contracted or not: `FakeJitterGenerator` and `FakeFreeSpaceMeter` in block 20, `FakeTrackedDownloadStore`
  in block 50, `FakeRunStateStore` in block 60. Why: the rule is written for all doubles, and the lot should not end
  with the tree breaking it.
- **D17. Every test of a double moves beside its double**, by D14's reason: `C/tests/adapters/driven/amule_api/
  test_api_fakes.py` (`FakeAmuleApiServer`, 62 lines) becomes `C/tests/fakes/test_fake_amule_api_server.py` in block 10;
  what block 80 leaves of `C/tests/application/test_fakes.py` (one test each of `FakeDecisionReader`,
  `FakeNoSetStateTrackedDownloadStore`, `FakeBlockingMonotonicClock`) moves to a `test_<fake module>.py` beside each
  double, and the file goes. (Corrected: five doubles, not three: `FakeLogger`'s test too, and the catalog-reads test
  covered `FakeDecisionReader` and `FakeObservationReader`, split into one test each; block 80.) These are the only test files dedicated to doubles: the two are the only ones
  `tests_without_unit` lists for doubles, and a test file named after no `src` module fails `_unit-coverage-check`
  unless listed there (every package's `pyproject.toml`, 2026-10-25). A test of a double written inside a module's own
  test file would escape this count; none is known.

## Blocks

Estimates: the Sonnet agent `contract-estimates`, on the tree at `84d6c0fe`, 2026-10-25; the contract bodies are
guessed from appendix A and the tests they restate. (Corrected: the Measured column, each block's lines and files
against its parent branch, from its report.)

| # | Branch | Holds | Lines, files | Measured |
|---|--------|-------|--------------|----------|
| 10 | `test/contract-port-implementations` | this spec; `test_fake_files.py`'s AST helpers moved to `tests/support/port_implementations.py`; `test_api_fakes.py` moved beside its fake (D17); (Corrected: D14's skip and the two amended sentences) | 370, 5 | 268, 7 |
| 20 | `test/contract-subclasses-check` | the structure test; the `PolicyFingerprintStore` contract and its two subclasses; the assertion rewriting; C1 to C4 and the amended sentences in `AGENTS.md` and `testing.md` (Corrected: the sentences amended in block 10, this block adding `tests/contracts` to them); two docstrings (D5 to D8, D10, D14 to D16) | 400, 15 | 266, 15 |
| 30 | `test/node-id-store-contract` | the `NodeIdStore` contract; `FakeNodeIdStore` refuses a second id (D9) | 150, 7 | 69, 5 |
| 40 | `test/backoff-state-store-contract` | the `BackoffStateStore` contract; its port's aware read (A1) | 190, 6 | 96, 5 |
| 50 | `test/tracked-download-store-contract` | the `TrackedDownloadStore` contract and its exemption; its ports' silences (A1); `FakeTrackedDownloadStore`'s fix and docstring (D9, D15) | 360, 7 | 268, 8 |
| 60 | `test/run-state-store-contract` | the `RunStateStore` contract; its initial state in the port; `FakeRunStateStore`'s docstring (D15) | 210, 7 | 214, 8 |
| 70 | `test/status-reading-store-contract` | the `StatusReadingStore` contract; its listed clients in the port; `FakeStatusReadingStore` built with them (D9) | 150, 9 | 123, 8 |
| 80 | `test/monotonic-clock-contract` | the crawler's `MonotonicClock` contract and its exemption; its promises (D12); `virtual_time.py` hands out the loop it runs, so that `FakeLoopMonotonicClock` receives it (D9); `test_fakes.py`'s clock tests pruned, the rest moved beside its doubles (D10, D17) | 330, 17 | 340, 19 |
| 90 | `test/wall-clock-contract` | the crawler's `WallClock` contract; its promises (A1); `FakeLoopWallClock` receives its loop (D9) | 200, 9 | 82, 9 |
| 100 | `test/waker-contract` | the `Waker` contract | 100, 5 | 68, 4 |
| 110 | `test/amule-contracts` | amule's `AmuleConfStore` and `MonotonicClock` contracts; `FakeAmuleConfStore`'s read error (D9); amule's `tests_without_unit` and assertion rewriting | 280, 11 | 158, 14 |
| 120 | `test/dockerfile-store-contract` | amule_bump's `DockerfileStore` contract; its `tests_without_unit` and assertion rewriting | 120, 7 | 76, 9 |
| 130 | `docs/fake-contract-tests-wrap` | closing block: holistic findings, backlog, handoff | | 73, 18 |

- Order: the helpers' move first, then the check with its first contract, so that every later contract is checked as it
  lands. The check covers only the ports a suite exists for, so each later block adds a suite, all its subclasses and its
  exemptions together.
- Blocks 80 and 90 were one, estimated at 400 lines and 17 files before `virtual_time.py`'s change was known: split
  ahead. Rows 10, 20, 80, 90, 110 and 120 were raised by the lead after the review and D17, from the files they add;
  block 80 at 17 files is the soft spot: if it passes 19, `test_fakes.py`'s dispersal moves to block 90. (Corrected:
  block 80 measured 19 files, within the bound, D17's five doubles instead of three adding the two.)

## Acceptance

1. Deleting one subclass, or its fixture, or adding a stale exemption, makes `test_contract_subclasses.py` fail naming the
   implementation, the subclass or the exemption; restoring it makes it pass. Block 20's report quotes the three runs.
2. Each fake fix of D9 is preceded by its contract test failing on the unfixed fake, the failing line coming from a
   test's body (for `FakeStatusReadingStore`, after its subclass is built with the new constructor and before the fake keeps
   its client names); the block's report quotes it.
3. `uv run pytest --collect-only -q --no-cov`, run in each of C, A and B, lists a test under each of the 28 subclasses of
   A2.
4. `git diff origin/main...<top> --stat -- 'packages/*/src'` lists only these files, under
   `application/ports/driven/`, and each one's diff changes docstrings only: C's `tracked_download_writer.py`,
   `tracked_download_reader.py`, `backoff_state_reader.py`, `run_state_reader.py`, `status_reading_reader.py`,
   `monotonic_clock.py`, `wall_clock.py`; A's `monotonic_clock.py`. (Corrected: the pathspec is
   `'packages/*/src/*'`, since `'packages/*/src'` matches nothing; and the closing block rewords, docstrings only, the
   seven `src` files whose docstrings used "contract" in another sense than the glossary's: C's
   `domain/client_errors.py`, `domain/store_error.py`, `adapters/driven/persistence_sqlite/errors.py`,
   `adapters/driven/amule_api/errors.py`, `application/steps/cataloguer.py`, `application/steps/file_judge.py`, and
   `packages/matching/src/catalog_matching/domain/combinators.py`.)
5. `grep -rniE "the real|Sqlite|Asyncio|InMemory|Posix|Filesystem|System[A-Z]|AmuleApi|Github|S6|Shutil|Stdlib|Random[A-Z]|Apprise|Gluetun|Prometheus|Uuid4"
   packages/*/tests/fakes` prints no docstring or comment line. (Corrected: as worded, it printed the docstrings and
   comments of the outside systems' fakes at `tests/fakes`' root, which describe the system they replace, and,
   case-insensitive, `asyncio` code lines. Narrowed to the doubles of ports: case-sensitive, over `tests/fakes`'
   subdirectories, without the two doubles of what an adapter receives, `FakeCommandRunner` and `FakeApprise`:
   `grep -rnE "[Tt]he real|[Ss]qlite|SQLite|Asyncio|InMemory|Posix|Filesystem|System[A-Z]|AmuleApi|amuleapi|Git[Hh]ub|S6|s6|Shutil|Stdlib|Random[A-Z]|Apprise|[Gg]luetun|Prometheus|Uuid4" packages/*/tests/fakes/*/ --exclude=fake_command_runner.py --exclude=fake_apprise.py`
   printed nothing (exit 1) at the closing block, 2026-10-25; on `84d6c0fe` it printed the two docstrings the lot
   rewrote, of `FakeTrackedDownloadStore` and `FakeRunStateStore`.)
6. The closing block's report holds a table with one row per A1 row: for a silence relied on, the port line that states
   it and the contract test that tests it; for one left unspecified, the absence of both.
7. `AGENTS.md` carries C1 to C4, names `tests/contracts` beside `tests/fakes` and `tests/support`, and no longer says
   `tests/fakes` holds no `test_*.py`; `docs/contributing/testing.md` explains the contracts.
8. Nothing out of scope changes: `deploy/`, `security/`, the Dockerfiles, `.github/`, the migrations, any `src` code.
9. `uv run poe check` passes at every block's tip.

## Backlog

- **Contract tests for the fakes**: this lot; the closing block deletes the entry.
- **Contract tests for the fakes of outside systems**: added by this Discuss; stays open, its real side is an outside
  system run only under the integration markers.
- **Stubs and spies written with decoy**: added by this Discuss; follows this lot. It takes `FakeSourcePointStore`, the
  refusals of `FakeDecisionReader` and `FakeObservationReader`, and amends the naming rule, since stubs and spies keep
  the `Fake` prefix until then.
- **Test quality** and **Mutation testing in the gate**: stay open; this lot prunes only what a contract restates.
- Untouched, staying open: **A copy before a migration that rewrites rows**, **The metrics served by the webui on 8080**,
  **Every stamp an integer of microseconds**, **The ast-grep rule tests bound to their rules by design**, **The node
  page shows a node id set in `crawler.yml`**, **The VEX's Python claims applied by Grype**, **The Grype scan back on
  p2pwatch at the v5 release**, **Multi network**, **Sort the files view by first seen**, **The webui in the visitor's
  time zone**, **Adopt ty**.

## Appendix A: the contracts

### A1. Each port's silences and their verdicts

"Relied on" names the production call site that relies; each was found by a search of the method names over every
`src` tree (appendix B). Paths are under `C/src/p2pwatch/` unless prefixed `A/`.

| Port or store | Silence | Verdict |
|---|---|---|
| `TrackedDownloadStore` | `set_seen` of an untracked file: no error, no row created | relied on (`application/steps/download_tracker.py:75` passes the client's whole list, foreign downloads included): stated |
| `TrackedDownloadStore` | `read_latest_seen_at_by_file` gives a queued download never seen its `queued_at` | relied on (`download_tracker.py:164-172`, the loss deadline after a restart): stated |
| `TrackedDownloadStore` | `set_state`, `set_completed` on an untracked file | unspecified (every call follows a read that found the file tracked) |
| `NodeIdStore` | the first id survives a refused second | unspecified (`node_id_resolver.py:31-35` records once, after a `None` read) |
| `BackoffStateStore`, `TrackedDownloadStore` | a read instant is aware UTC | relied on (`remaining_wait` subtracts it from an aware `now`, `download_tracker.py:171`, `backoff_registry.py:56`): stated |
| `BackoffStateStore`, `NodeIdStore`, `TrackedDownloadStore` | a naive instant written is refused | unspecified (every instant written comes from `WallClock.now()`) |
| `BackoffStateStore` | the refusal of `attempts < 1` and `delay < 0` | unspecified (`backoff_registry.py:80-90` never builds one) |
| `RunStateStore` | starts resumed, without a shutdown request | relied on (the composition never sets it; `search_task_runner.py:60`, `download_loop.py:38`): stated |
| `StatusReadingStore` | lists every client it was built with, `None` before its first reading | relied on (`summarize_crawl.py:38-48` shows a configured client before its first reading): stated |
| `Waker` | a `wake` with no waiter is kept for the next `wait` | unspecified (a lost wake costs at most `poll_interval`, which the port's module docstring calls harmless) |
| `Waker` | a wake of one subject leaves another's waiters asleep | unspecified (`WakeSubject` has one member) |
| `MonotonicClock` (C and A) | `now()` never decreases | relied on (every deadline and age): stated |
| `MonotonicClock` (C and A) | `sleep(d)` then `now()` at least `d` later, less one microsecond | relied on approximately (`search_task_runner.py:61-64` re-checks): stated (D12) |
| C's `MonotonicClock` | `now()` callable from any thread, no running loop needed | relied on (`summarize_crawl.py:39`, on the webui's thread): stated |
| `WallClock` | `now()` callable from any thread, no running loop needed | relied on (`describe_file.py:38`, `describe_source.py:30`, `describe_source_name.py:33`, called from the webui's handlers): stated |
| `WallClock` | `now()` never decreases | unspecified (`remaining_wait` clamps a step back) |
| `DockerfileStore` | a write into a missing directory | unspecified (`B/.../bump_amule.py:68-69` writes the path it just read) |
| `StatusReadingStore` | a reading set for a client the store was not built with | unspecified (the status loop sets only its own configured client). (Corrected: row added by block 70.) |
| `StatusReadingStore` | a read is a snapshot a later write never changes | unspecified (the in-memory store's mechanism, kept in its own test). (Corrected: row added by block 70.) |

Already stated, kept and tested (D4): `record_queued` keeps an already tracked file's row; a second node id is refused;
the run state's waits return at once when already resumed or requested; `read_amule_conf` raises `OSError` when the
file exists but cannot be read (relied on by `A/application/port_sync_lifecycle.py:56-65`). (Corrected: also tested as
stated, by the blocks named: each run state writer method changes its own state only, a pause requesting no shutdown
and a shutdown request leaving the crawler resumed, and both run state ports' "any thread" (60); the status reading's
replacement and its read from any thread (70). The closing block tests port-sync's `OSError` side through
`FakeAmuleConfStore`'s `read_error`.)

### A2. The suites and their subclasses

| Suite | Package | Subclasses | Exempt |
|---|---|---|---|
| `PolicyFingerprintStoreContract` | C | `TestSqlitePolicyFingerprintStore`, `TestFakePolicyFingerprintStore` | |
| `NodeIdStoreContract` | C | `TestSqliteNodeIdStore`, `TestFakeNodeIdStore` | |
| `BackoffStateStoreContract` | C | `TestSqliteBackoffStateStore`, `TestFakeBackoffStateStore` | |
| `TrackedDownloadStoreContract` | C | `TestSqliteTrackedDownloadStore`, `TestFakeTrackedDownloadStore` | `FakeNoSetStateTrackedDownloadStore` |
| `RunStateStoreContract` | C | `TestAsyncioRunStateStore`, `TestFakeRunStateStore` | |
| `StatusReadingStoreContract` | C | `TestInMemoryStatusReadingStore`, `TestFakeStatusReadingStore` | |
| `MonotonicClockContract` | C | `TestAsyncioMonotonicClock`, `TestFakeMonotonicClock`, `TestFakeTickingMonotonicClock`, `TestFakeLoopMonotonicClock` | `FakeBlockingMonotonicClock` |
| `WallClockContract` | C | `TestSystemWallClock`, `TestFakeWallClock`, `TestFakeTickingWallClock`, `TestFakeLoopWallClock` | |
| `WakerContract` | C | `TestAsyncioWaker`, `TestFakeWaker` | |
| `AmuleConfStoreContract` | A | `TestPosixAmuleConfStore`, `TestFakeAmuleConfStore` | |
| `MonotonicClockContract` | A | `TestSystemMonotonicClock`, `TestFakeMonotonicClock` | |
| `DockerfileStoreContract` | B | `TestFilesystemDockerfileStore`, `TestFakeDockerfileStore` | |

Twelve suites, 28 subclasses, two exemptions.

### A3. What each suite needs

- The SQLite stores build on `open_local(tmp_path / "local.db")` and close the connection after, since an unclosed
  connection fails a test (`pytest_settings`' `ResourceWarning` filter).
- `RunStateStoreContract`, `WakerContract` and the crawler's clocks are async (`@pytest.mark.asyncio`, strict mode); a
  write to the run state is read after one `await asyncio.sleep(0)`, which lets `call_soon_threadsafe`'s callback run
  first in asyncio's FIFO ready queue.
- The "any thread" promises of both crawler clocks are tested by calling `now()` from a thread with no running loop.
- `AmuleConfStoreContract`'s failing read: the real store reads a path that is a directory (`IsADirectoryError`, an
  `OSError` even as root), the fake its new read error.
- The fake clocks build on a `FakeTime`; `FakeLoopMonotonicClock` and `FakeLoopWallClock` on the loop `virtual_time.py`
  hands out. Their only users are `test_amule_api_client_search_pacing.py` and `test_search_task_runner.py`.
  (Corrected: their contract subclasses build them on pytest-asyncio's running loop, since the contract is async and the
  virtual loop cannot wait on a thread, which the thread test needs; their users still hand them the virtual loop.
  Blocks 80 and 90.)
- (Corrected: amule's `MonotonicClockContract` compares `now().nanoseconds`, since amule's `MonotonicInstant` is not
  ordered and its difference rounds a sub-microsecond step to zero; block 110.)
- `FakeTime` is never given a naive `start` in the tree, so `FakeWallClock` is aware in every configuration a test uses.

## Appendix B: measurements

- Inventory, 2026-10-25, by AST over every `*/src` and `*/tests` with `test_fake_files.py`'s resolution, recounted by the
  review: the implementations of the contracted ports are exactly the 28 classes of A2 and the two exemptions (24 in C,
  4 in A, 2 in B); no class outside `tests/fakes` implements one (`C/tests/test_fake_files.py:222`). No first-party base
  is written `module.Class`, no import is relative, and no `__init__.py` re-exports.
- Fakes against their ports, read from their code: `FakeNodeIdStore.record_node_id` never refuses a second id
  (`fake_node_id_store.py:19-21`); `FakeTrackedDownloadStore.record_queued` overwrites a tracked file's row
  (`fake_tracked_download_store.py:52-61`); `FakeSourcePointStore`'s three reads return constructor values
  (`fake_source_point_store.py:54, 61, 68`); `FakeLoopMonotonicClock.now` and `FakeLoopWallClock.now` read the running
  loop (`fake_loop_monotonic_clock.py:13`, `fake_loop_wall_clock.py:12`).
- No test depends on `FakeTrackedDownloadStore`'s overwrite on a re-queue, nor on `set_state` or `set_completed` creating
  a row: in a scratch copy of `C/tests`, the fake changed to keep the row and to raise `StoreError` for an untracked
  file, the eight user files passed (97 tests) under each change and both; a control making `record_queued` a no-op
  failed 8 tests, so the changed fake was the one run. No test makes a second `record_node_id` on `FakeNodeIdStore`
  (`node_id_resolver.py` records once).
- pytest 9.1.1 collects no test from a test class that inherits an abstract fixture without defining it, and warns
  nothing, even under `-W error`: a scratch suite with one concrete and one abstract subclass collected 1 test
  (`pytest --collect-only -q -W error`). The same suite passes `mypy --strict`.
- pytest does not rewrite the assertions of a test class imported from a non-test module: a failing `assert {"a": 1} ==
  {"a": 2}` there prints a bare `AssertionError` (the review, reproduced).
- asyncio fires a timer up to `_clock_resolution` early (`asyncio/base_events.py:2018`), 1 ns on the measuring machine.

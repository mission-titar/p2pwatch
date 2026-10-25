# Handoff: contract tests for the fakes

Drafted by block 120 from the lot's block reports (#476, #477, #479 to #488), corrected by the closing block 130 with
the holistic review (`.reviews/fake-contract-tests-holistic.md`).

## State

Tier Spec lot. Spec `agents/specs/2026-10-25-fake-contract-tests.md` (approved 2026-10-25, after the review
`contract-spec-review`; its claims the lot made false now carry their `(Corrected: ...)`). It ships the backlog entry
"Contract tests for the fakes", deleted from `BACKLOG.md` by block 130.

One stack cut from `main` at `84d6c0fe`, which had not moved when block 130 was written. Thirteen blocks with the
closing one, as the spec's table planned: no split, no insertion, no exemption.

| Block | Pull request | Branch |
|---|---|---|
| 10 | #476 | `test/contract-port-implementations` |
| 20 | #477 | `test/contract-subclasses-check` |
| 30 | #479 | `test/node-id-store-contract` |
| 40 | #480 | `test/backoff-state-store-contract` |
| 50 | #481 | `test/tracked-download-store-contract` |
| 60 | #482 | `test/run-state-store-contract` |
| 70 | #483 | `test/status-reading-store-contract` |
| 80 | #484 | `test/monotonic-clock-contract` |
| 90 | #485 | `test/wall-clock-contract` |
| 100 | #486 | `test/waker-contract` |
| 110 | #487 | `test/amule-contracts` |
| 120 | #488 | `test/dockerfile-store-contract` |
| 130 | the closing block's | `docs/fake-contract-tests-wrap` |

Not merged at writing. The lot changes tests, test support and `src` docstrings only (eight port files, and seven
files where "contract" took another sense), so it ships nothing and no release follows it.

## What was built

- **The machinery** (blocks 10, 20, 130; D8, D14, D17): `test_fake_files.py`'s AST helpers public in
  `C/tests/support/port_implementations.py`. `test_contract_subclasses.py` makes five checks over every package: each
  contract covers ports of its own package; each implementation of a contracted port in `src` or `tests/fakes` has its
  `Test<Implementation>` subclass or a named exemption; each subclass sits in its implementation's own test module
  (130); each subclass defines its suite's abstract fixtures (`async def` ones included since block 60); no exemption
  is stale. `test_fake_files.py` skips the `test_*.py` of `tests/fakes` when it looks for doubles, and since block 130
  its stray-class check treats them as outside the fakes. `FakeAmuleApiServer`'s tests moved beside it.
- **The conventions** (blocks 20, 130): C1 to C4 in `AGENTS.md` (Hard rules and the glossary's `fake`, `stub`, `spy`,
  `contract`), `tests/contracts` beside `tests/fakes` and `tests/support`, the amuleapi adapter's "error mapping",
  `docs/contributing/testing.md` explaining the contracts; each package's root `conftest.py` registers
  `tests.contracts` for assertion rewriting. Block 130 adds the pair's `Protocol` to C1 and the five checks to both
  texts, and rewords the seven `src` docstrings that used "contract" in another sense.
- **Twelve suites, 28 subclasses, two exemptions** (blocks 20 to 120, appendix A2): the crawler's
  `PolicyFingerprintStore`, `NodeIdStore`, `BackoffStateStore`, `TrackedDownloadStore` (exempting
  `FakeNoSetStateTrackedDownloadStore`), `RunStateStore`, `StatusReadingStore`, `MonotonicClock` (exempting
  `FakeBlockingMonotonicClock`), `WallClock` and `Waker`; amule's `AmuleConfStore` and `MonotonicClock`; amule_bump's
  `DockerfileStore`. A Writer/Reader pair's contract declares a `Protocol` of the pair, `<Thing>Store`, to type its
  fixture.
- **The ports' promises** (D4, A1): the docstrings of `TrackedDownloadWriter.set_seen` and
  `TrackedDownloadReader.read_latest_seen_at_by_file` (block 50), `BackoffStateReader`'s aware read (40),
  `RunStateReader`'s initial state (60), `StatusReadingReader`'s listed clients (70), both `MonotonicClock`s' order and
  sleep to the microsecond (80, 110), `WallClock`'s any thread (90).
- **The fakes fixed** (D9, each watched failing first): `FakeNodeIdStore` refuses a second id (30);
  `FakeTrackedDownloadStore` keeps a re-queued file's row (50); `FakeStatusReadingStore(client_names)` (70);
  `FakeLoopMonotonicClock` and `FakeLoopWallClock` receive their loop (80, 90); `FakeAmuleConfStore.read_error` (110),
  which also drives port-sync's `OSError` side on the conf read since block 130. `FakeImmediateEventLoop`, left
  without a user, deleted (60).
- **Docstrings against the port** (D15): `FakeJitterGenerator`, `FakeFreeSpaceMeter` (20), `FakeNodeIdStore` (30),
  `FakeTrackedDownloadStore` (50), `FakeRunStateStore` (60).
- **`virtual_time.py`** (80): hands out its loop as the `virtual_loop` fixture, registered in the crawler's
  `conftest.py`; `run_virtual` gone; the search task runner's tests share one loop clock.
- **Pruned** (D10): the real adapters' tests each contract restates (SQLite stores, the asyncio run state store and
  waker, the in-memory status store, the clocks, amule's conf store, amule_bump's Dockerfile store's read and absent
  read); `test_fakes.py`'s two `FakeTime` tests, the rest of that file moved beside its doubles (D17) and the file gone.
  Block 130 restored `AsyncioMonotonicClock`'s bounded read, which no contract restates.

## Acceptance

Measured by block 120 at `3370af0b`, or by block 130 at its tip, unless a block is named.

1. Block 20: the subclass deleted, the fixture deleted and a stale exemption each fail `test_contract_subclasses.py`
   naming the implementation, the subclass or the exemption (`1 failed, 3 passed` each); restored, `4 passed`.
2. Blocks 30, 50, 70, 80, 90, 110: each fix preceded by its contract failing in a test's body (`DID NOT RAISE
   StoreError` at `node_id_store_contract.py:37`; `'063A' != '062A'` at `tracked_download_store_contract.py:90`;
   `assert {} == {'amuled': No...'emule': None}` at `status_reading_store_contract.py:38`; `RuntimeError: no running
   event loop` at `monotonic_clock_contract.py:41` and `wall_clock_contract.py:26`; `DID NOT RAISE OSError` at
   `amule_conf_store_contract.py:45`).
3. `pytest --collect-only -q --no-cov` in C, A and B lists a test under each of the 28 subclasses of A2 (28 distinct
   class names in the three outputs, `TestFakeMonotonicClock` once in C and once in A).
4. Block 130: `git diff origin/main...HEAD --stat -- 'packages/*/src/*'` lists 15 files, 28 insertions and 20
   deletions, docstrings only: the eight port files of acceptance 4 (18 and 10, per each block's report) and the seven
   files block 130 reworded (acceptance 4's correction). The pathspec `'packages/*/src'` matches nothing.
5. Block 130, the grep narrowed to the doubles of ports (acceptance 5's correction): case-sensitive, over
   `packages/*/tests/fakes/*/`, without `fake_command_runner.py` and `fake_apprise.py`, it prints nothing (exit 1). On
   `84d6c0fe` it prints the docstrings of `FakeTrackedDownloadStore` and `FakeRunStateStore` the lot rewrote.
6. Block 130's report: the table of A1's rows.
7. Block 20 (`AGENTS.md`, `testing.md`), completed by block 130.
8. `git diff origin/main...HEAD --stat` over `deploy`, `security`, `.github`, both Dockerfiles and the migrations prints
   nothing (block 120); block 130 touches none of them.
9. The gate green at every block's tip (each report; block 130: `uv run poe check` exit 0, crawler 1615 passed).

## The holistic review's findings

Every finding exited fixed in the lot, in block 130.

| Severity | Finding | Exit |
|---|---|---|
| MAJOR | D14's skip hid a port's implementation in a `tests/fakes/**/test_*.py` from all three structure checks | Fixed: the stray-class check of `test_fake_files.py` treats such a file as outside the fakes. The review's mutation (`FakeHiddenNodeIdReader(NodeIdReader)` in `test_fake_node_id_store.py`) gave `9 passed` before, `1 failed, 8 passed` after, naming the class |
| MAJOR | The spec carried no `(Corrected: ...)` for the claims the lot made false | Fixed: 18 corrections (D8, D10, D14, D17, C1, C2, A1, A3, acceptance 4 and 5, the block table with a Measured column, the operator-facing paragraph) |
| MINOR | Nothing checked that a subclass sits in its implementation's own test module | Fixed: a fifth structure test. A fake's subclass moved to `tests/application/test_moved_subclass.py`, and a SQLite store's subclass moved up a directory, each failed it naming the subclass and its expected file |
| MINOR | `AsyncioMonotonicClock`'s bounded read pruned, a wall clock read passing every test | Fixed: `test_now_reads_the_system_monotonic_clock` restored. With `time.time_ns()` in the adapter it failed at its assertion (`1792933408320212137 <= 1957676995056143`) |
| MINOR | The pair's `Protocol` recorded nowhere | Fixed: C1 in `AGENTS.md` and `testing.md` |
| MINOR | Three structure checks named where the code made four | Fixed: both texts name the five checks |
| MINOR | Three `src` docstrings used "contract" in another sense | Fixed, with four more found by `grep -rni contract packages/*/src` (class 1): seven files, docstrings only |
| MINOR | Two stale lines of the handoff's "Not validated" | Fixed: both removed, the runs recounted |
| MINOR | The coverage comment of three `pyproject.toml` left out the contracts | Fixed |
| MINOR | `last` without `first` in two tracked download contract tests | Fixed: `..._read_as_seen_when_queued`, `..._read_at_its_latest_listing` |

## Departures from the spec

- Block 10: D14's skip and the two amended sentences landed here, not in 20; the helpers public, the doubles-only ones
  kept in `test_fake_files.py`.
- Block 20: the `Protocol` of the pair per store contract; a fourth structure test (a contract covering no port of its
  package); exemptions keyed by the `shown` path (`FakeMonotonicClock` exists in C and A); `first_party_bases` public.
- Block 30: 5 files, no port docstring change; the SQLite later-instance read kept, cut to it.
- Block 40: 5 files, the fake unchanged; the UTC test asserts a zero offset, not the `tzinfo` identity.
- Block 50: 8 files (the exemption and `tests_without_unit` count); `set_state`, `set_completed` on an untracked file
  and a naive instant left unspecified, the SQLite refusal kept in its own tests.
- Block 60: 8 files, `FakeImmediateEventLoop` deleted; the structure test reads `async def` fixtures; each writer
  method changing only its own state, and the "any thread" of both ports, tested as stated.
- Block 70: the writer's replacement and the reader's any thread tested as stated; a reading for a client not built
  with, and a read being a snapshot, left unspecified (two A1 rows added by block 130); the contract exports
  `CLIENT_NAMES`.
- Blocks 80, 90: `TestFakeLoopMonotonicClock` and `TestFakeLoopWallClock` build their fake on pytest-asyncio's
  running loop, not on `virtual_time.py`'s (A3, corrected): the contract is async, and the virtual loop cannot wait on
  a thread.
- Block 80: five doubles left in `test_fakes.py`, not three (D17 missed `FakeLogger`, and the catalog-reads test
  covered two doubles), hence 19 files.
- Block 90: the thread test asserts the reading's zone, not an order (A1 leaves the order unspecified).
- Block 100: 4 files, the port already stating both promises.
- Block 110: 14 files, four of them the empty `__init__.py` of `tests/contracts`; amule's clock contract compares
  `now().nanoseconds` (amule's `MonotonicInstant` is not ordered); `AmuleConfStoreContract` has a second abstract
  fixture, `unreadable_amule_conf_store`; the fake raises `read_error` before recording the read.
- Block 120: 9 files, four of them empty `__init__.py`; the contract's `dockerfile_path` is a concrete fixture
  (`tmp_path / "Dockerfile"`), one abstract fixture only; the real store keeps
  `test_set_dockerfile_replaces_the_file_s_text`, which reads the file on disk, as block 110 kept its on-disk tests.
- Block 130: seven `src` docstrings reworded where the review named three (class 1 below); acceptance 5's grep made
  case-sensitive besides narrowed, since `-i` matched `asyncio` code.

## Class 1 fixes

- Block 40: `test_backoff_states_round_trip_through_a_new_repo_instance` renamed
  `test_the_backoff_states_saved_are_read_back_by_any_later_instance` (`repo` is no glossary word).
- Block 100: `test_asyncio_waker.py`'s tests renamed from `signal` to `wake`, `hub` to `waker`.
- Block 130: four `src` docstrings beyond the review's three used "contract" for an error type
  (`persistence_sqlite/errors.py` twice, `amule_api/errors.py`, `cataloguer.py`, `file_judge.py`), reworded with them.

## Class 2 questions

None in any block.

## Pitfalls

- **pytest 9.1.1 silently skips a test class left abstract** (appendix B), and `@pytest.fixture` over `@abstractmethod`
  keeps the class abstract; mypy accepts a subclass fixture asking for more fixtures than the abstract one (block 20).
- **`register_assert_rewrite` must run before the contract's first import**: in the package's root `conftest.py`
  (block 20).
- **Under strict asyncio mode a fixture needing the running loop is `@pytest_asyncio.fixture async def`**;
  `pytestmark = pytest.mark.asyncio` on the contract marks every inherited test (block 60).
- **The virtual loop cannot wait on a thread**: its selector never blocks, so with no timer set it reports a deadlock
  (block 80).
- **amule's `MonotonicInstant.__sub__` rounds a sub-microsecond difference to zero**: compare nanoseconds where the
  sign matters (block 110).
- **Making helpers public can shadow them**: `class_def = class_def(definition)` raises `UnboundLocalError`; rename the
  locals (block 10).
- **A skip in one structure check is a hole in the others**: the doubles check's skip of `tests/fakes/**/test_*.py`
  left the stray-class check exempting the same files (block 130).
- **A case-insensitive grep for adapter names matches code**: `-i` turns `Asyncio` into every `asyncio.` line
  (block 130).
- `FakeTrackedDownloadStore`'s re-queue check reads `states`, so a file given a state without being queued counts as
  tracked (block 50, unspecified).

## Not validated

- Continuous integration of block 130 at writing; #476 to #488 each passed their one run.

## Wrap counts

From `gh run list --branch <branch> --workflow PR`, 2026-10-25: one run per branch for blocks 10 to 120, all
successful. No fix-back, no cascaded rebase, no run re-triggered, no body called unreadable. Recount after the rebase
onto `main` before the merge, if `main` has moved.

## Next

- The operator reads the stack; the lead rebases it onto the current `main`; the operator merges it.
- Then the backlog, "A copy before a migration that rewrites rows" first, or "Stubs and spies written with decoy",
  which follows this lot.

# Handoff: contract tests for the fakes

Drafted by block 120 from the lot's block reports (#476, #477, #479 to #487) and its own, for the closing block 130
to correct with the holistic review.

## State

Tier Spec lot. Spec `agents/specs/2026-10-25-fake-contract-tests.md` (approved 2026-10-25, after the review
`contract-spec-review`). It ships the backlog entry "Contract tests for the fakes".

One stack cut from `main` at `84d6c0fe`. Thirteen blocks with the closing one, as the spec's table planned: no split,
no insertion, no exemption.

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
| 120 | (this block's) | `test/dockerfile-store-contract` |
| 130 | closing | `docs/fake-contract-tests-wrap` |

Not merged at writing. The lot changes tests, test support and eight port docstrings only, so it ships nothing and no
release follows it.

## What was built

- **The machinery** (blocks 10, 20, D8, D14, D17): `test_fake_files.py`'s AST helpers public in
  `C/tests/support/port_implementations.py`; `test_contract_subclasses.py` checks, for every package, that each
  implementation of a contracted port in `src` or `tests/fakes` has its `Test<Implementation>` subclass or a named
  exemption, that each subclass defines its suite's abstract fixtures (`async def` ones included since block 60), that
  no exemption is stale, and that each contract covers ports of its own package. `test_fake_files.py` skips the
  `test_*.py` of `tests/fakes`; `FakeAmuleApiServer`'s tests moved beside it.
- **The conventions** (block 20): C1 to C4 in `AGENTS.md` (Hard rules and the glossary's `fake`, `stub`, `spy`,
  `contract`), `tests/contracts` beside `tests/fakes` and `tests/support`, the amuleapi adapter's "error mapping",
  `docs/contributing/testing.md` explaining the contracts; each package's root `conftest.py` registers
  `tests.contracts` for assertion rewriting.
- **Twelve suites, 28 subclasses, two exemptions** (blocks 20 to 120, appendix A2): the crawler's
  `PolicyFingerprintStore`, `NodeIdStore`, `BackoffStateStore`, `TrackedDownloadStore` (exempting
  `FakeNoSetStateTrackedDownloadStore`), `RunStateStore`, `StatusReadingStore`, `MonotonicClock` (exempting
  `FakeBlockingMonotonicClock`), `WallClock` and `Waker`; amule's `AmuleConfStore` and `MonotonicClock`; amule_bump's
  `DockerfileStore`. A Writer/Reader pair's contract declares a small `Protocol` of the pair to type its fixture.
- **The ports' promises** (D4, A1): the docstrings of `TrackedDownloadWriter.set_seen` and
  `TrackedDownloadReader.read_latest_seen_at_by_file` (block 50), `BackoffStateReader`'s aware read (40),
  `RunStateReader`'s initial state (60), `StatusReadingReader`'s listed clients (70), both `MonotonicClock`s' order and
  sleep to the microsecond (80, 110), `WallClock`'s any thread (90).
- **The fakes fixed** (D9, each watched failing first): `FakeNodeIdStore` refuses a second id (30);
  `FakeTrackedDownloadStore` keeps a re-queued file's row (50); `FakeStatusReadingStore(client_names)` (70);
  `FakeLoopMonotonicClock` and `FakeLoopWallClock` receive their loop (80, 90); `FakeAmuleConfStore.read_error` (110).
  `FakeImmediateEventLoop`, left without a user, deleted (60).
- **Docstrings against the port** (D15): `FakeJitterGenerator`, `FakeFreeSpaceMeter` (20), `FakeNodeIdStore` (30),
  `FakeTrackedDownloadStore` (50), `FakeRunStateStore` (60).
- **`virtual_time.py`** (80): hands out its loop as the `virtual_loop` fixture, registered in the crawler's
  `conftest.py`; `run_virtual` gone; the search task runner's tests share one loop clock.
- **Pruned** (D10): the real adapters' tests each contract restates (SQLite stores, the asyncio run state store and
  waker, the in-memory status store, the clocks, amule's conf store, amule_bump's Dockerfile store's read and absent
  read); `test_fakes.py`'s two `FakeTime` tests, the rest of that file moved beside its doubles (D17) and the file gone.

## Acceptance

Measured by block 120 at `3370af0b` unless a block is named.

1. Block 20: the subclass deleted, the fixture deleted and a stale exemption each fail `test_contract_subclasses.py`
   naming the implementation, the subclass or the exemption (`1 failed, 3 passed` each); restored, `4 passed`.
2. Blocks 30, 50, 70, 80, 90, 110: each fix preceded by its contract failing in a test's body (`DID NOT RAISE
   StoreError` at `node_id_store_contract.py:37`; `'063A' != '062A'` at `tracked_download_store_contract.py:90`;
   `assert {} == {'amuled': No...'emule': None}` at `status_reading_store_contract.py:38`; `RuntimeError: no running
   event loop` at `monotonic_clock_contract.py:41` and `wall_clock_contract.py:26`; `DID NOT RAISE OSError` at
   `amule_conf_store_contract.py:45`).
3. `pytest --collect-only -q --no-cov` in C, A and B lists a test under each of the 28 subclasses of A2 (28 distinct
   class names in the three outputs, `TestFakeMonotonicClock` once in C and once in A).
4. `git diff origin/main...HEAD --stat -- 'packages/*/src/*'` lists exactly the eight files of acceptance 4, 18
   insertions and 10 deletions, docstrings only per each block's report. Pitfall: the pathspec `'packages/*/src'`
   matches nothing; the trailing `/*` is needed.
5. Not met as worded: the grep still prints docstring and comment lines of outside systems' fakes, which describe the
   system they replace, not another implementation (`fake_amule_api.py:26`, `fake_amule_api.py:1`,
   `fake_amule_api_server.py:13`, `test_fake_amule_api_server.py:1`, `fake_command_runner.py:7`,
   `fake_gluetun_control_server.py:8`, and per block 20 `fake_notification_sink.py:6`, `fake_github_server.py:11`).
   Every touched contracted fake's grep printed no such line. For the closing block: narrow the grep, or accept it.
6. For the closing block: the table of A1's rows.
7. Block 20 (`AGENTS.md`, `testing.md`).
8. `git diff origin/main...HEAD --stat` over `deploy`, `security`, `.github`, both Dockerfiles and the migrations prints
   nothing; no `src` code changes (acceptance 4).
9. The gate green at every block's tip (each report); this block's run below.

## Departures from the spec

- Block 10: D14's skip and the two amended sentences landed here, not in 20; the helpers public, the doubles-only ones
  kept in `test_fake_files.py`.
- Block 20: the `Protocol` of the pair per store contract; a fourth structure test (a contract covering no port of its
  package); exemptions keyed by the `shown` path (`FakeMonotonicClock` exists in C and A); `first_party_bases` public.
- Block 30: 5 files, no port docstring change; the SQLite later-instance read kept, cut to it.
- Block 40: 5 files, the fake unchanged; the UTC test asserts a zero offset, not the `tzinfo` identity.
- Block 50: 8 files (the exemption and `tests_without_unit` count); `set_state`, `set_completed` on an untracked file
  and a naive instant left unspecified, the SQLite refusal kept in its own tests.
- Block 60: `FakeImmediateEventLoop` deleted; the structure test reads `async def` fixtures; each writer method changing
  only its own facet, and the "any thread" of both ports, tested as stated.
- Block 70: the writer's replace and the reader's any thread tested as stated; a reading for a client not built with,
  and a read being a snapshot, left unspecified; the contract exports `CLIENT_NAMES`.
- Blocks 80, 90: `TestFakeLoopMonotonicClock` and `TestFakeLoopWallClock` build their fake on pytest-asyncio's
  running loop, not on `virtual_time.py`'s (A3): the contract is async, and the virtual loop cannot wait on a thread.
  A3 may want its `(Corrected: ...)`.
- Block 80: five doubles left in `test_fakes.py`, not three (D17 missed `FakeLogger`, and the catalog-reads test
  covered two doubles), hence 19 files.
- Block 90: the thread test asserts the reading's zone, not an order (A1 leaves the order unspecified).
- Block 110: amule's clock contract compares `now().nanoseconds` (amule's `MonotonicInstant` is not ordered);
  `AmuleConfStoreContract` has a second abstract fixture, `unreadable_amule_conf_store`; the fake raises `read_error`
  before recording the read.
- Block 120: the contract's `dockerfile_path` is a concrete fixture (`tmp_path / "Dockerfile"`), one abstract fixture
  only; the real store keeps `test_set_dockerfile_replaces_the_file_s_text`, which reads the file on disk, as block 110
  kept its on-disk tests.

## Class 1 fixes

- Block 40: `test_backoff_states_round_trip_through_a_new_repo_instance` renamed
  `test_the_backoff_states_saved_are_read_back_by_any_later_instance` (`repo` is no glossary word).
- Block 100: `test_asyncio_waker.py`'s tests renamed from `signal` to `wake`, `hub` to `waker`.

## Class 2 questions

None in any block.

## For the closing block

- The holistic review, then acceptance 5's grep and acceptance 6's table.
- Port-sync's `except (OSError, ValueError)` on the conf read is tested only through `ValueError`; the new
  `read_error` knob could drive its `OSError` side in `test_port_sync_lifecycle.py` (block 110).
- `BACKLOG.md`: delete "Contract tests for the fakes"; "Contract tests for the fakes of outside systems" and "Stubs and
  spies written with decoy" stay (added by this lot's Discuss).

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
- `FakeTrackedDownloadStore`'s re-queue check reads `states`, so a file given a state without being queued counts as
  tracked (block 50, unspecified).

## Not validated

- Continuous integration of #487 and this block at writing; #476 to #486 each passed their one run.
- The real clocks' sleeps under load: 10 ms each, run 30 times green locally (blocks 80, 110); CI's runners are the
  first under load.

## Wrap counts

At writing, from `gh run list --branch <branch> --workflow PR`: one run per branch for blocks 10 to 100, all
successful; none listed yet for 110. No fix-back, no cascaded rebase, no re-push by a teammate. To recount at the
closing block, after the rebase onto `main`.

## Next

- The closing block 130: the holistic review's findings, the backlog, this handoff corrected.
- The operator reads the stack; the lead rebases it onto the current `main`; the operator merges it.
- Then the backlog, "A copy before a migration that rewrites rows" first, or "Stubs and spies written with decoy",
  which follows this lot.

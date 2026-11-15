# Handoff: v5 lot 4b2, the supervisor (tier Spec)

Drafted by block 60's teammate from the block reports (#767, #769, #771, #772, #773, #774, the collapsed "Block
report" of each pull request body). Corrected by the closing block, which also fixed the holistic review's findings
(`.reviews/v5-lot4b2-holistic.md`). Spec: `agents/specs/2026-11-15-v5-lot-4b-health-model.md`, lot 4b2 of its five
lots (D19), decisions D7, D17, D18.

## Current state

- **Every task the node repeats is a work** (`application/steps/work.py`): an abstract class with two methods,
  `wait_for_next_turn()` and `run_once()`. A work waits before each of its turns, the first one included, and
  computes that wait from its own state. It has no loop of its own.
- **One supervisor takes every work's turns** (`application/steps/supervisor.py`):
  `supervise(works, arm_shutdown_bound=...)` runs each work in its own task of one `TaskGroup`: its wait, its turn,
  then `asyncio.sleep(0)`, so a turn that never suspends cannot starve the other tasks. Once the run state says the
  shutdown was requested (a signal or the webui's restart button), it arms the shutdown's bound, then cancels every
  work. A turn that raises cancels every other work and ends the node, as on `main` (the spec's limit "During lot
  4b2"; lot 4b3 changes it).
- **The works, in the order the supervisor starts them** (`works_in_start_order` in `crawler_composition.py`), so the
  first status reading and the first download listing reach aMule before the first search, as on `main`:

  | Work | Module | Its wait |
  |---|---|---|
  | the status reading | `status_watcher.py` (`StatusWatcher`) | what is left of the minute since the latest reading ended, nothing before the first |
  | download tracking | `download_cycle.py` (`DownloadCycle`) | nothing before the first turn, then `download.poll_interval_seconds` or a download decision's wake, the first to come |
  | source tracking | `source_watcher.py` (`SourceWatcher`) | what is left of `download.sources_interval_seconds` since the previous turn started, nothing before the first |
  | one per client, channel and keyword, listed by `keyword_searches` | `keyword_search.py` (`KeywordSearch`) | until neither its client nor its channel is backed off, checked again after each sleep; a backoff the previous run saved delays the first search |

  The two download works exist only on a node with `download:`. Each lists the client's downloads itself.
- **A turn that raised stamps nothing.** The status watcher spaces its readings from the end of the latest one that
  returned, and download tracking's wait counts only a round that returned. Nothing reads a raised turn's stamp
  while a raise ends the node; lot 4b3, where a turn that raises no longer ends it, brings the stamp back with its
  first reader. Source tracking's start, stamped before its read, is the exception block 40's row asks for.
- **`BackoffSaver`** (`backoff_saver.py`), one for every search, sets the shared backoff in `local.db` after each
  turn that changed it. It takes its reference copy at the first search, since it is built before the lifecycle
  resumes the saved backoff. A refused save is logged and tried again after the next search, as on `main`.
- **`CrawlerLifecycle`** takes the works and hands them to the supervisor once the backoff is resumed, the node
  announced and the catalog re-evaluated.
- **Source tracking changed in two ways** (block 40, the operator's choice of 2026-11-12, written in
  `docs/settings.md`): its turns run `sources_interval` apart from start to start, where they waited the interval
  after each download round; the start is stamped before the read, so a failed read waits a full interval, where it
  was tried again one poll later. Nothing else changed in behaviour, but the two points below.
- **A turn may start after the shutdown request**, where `main`'s status and download loops read the run state before
  each round. When a turn's wait ends in the same pass of the event loop as the request, that turn starts, then is
  cancelled at its first `await`; no work writes before its first `await`, so nothing is written. Judged harmless
  (the holistic review's probe: `['shutdown requested', 'B turn started', 'armed']`).
- **`time_between_source_reads` keeps its `+ poll_interval_seconds`** as a plain margin, equal to one poll, so the
  carried role's window and the webui's period gap keep their values; no download round lies between two source
  reads since block 40 (`crawler_config.py`, `docs/settings.md`, `docs/contributing/architecture.md`).
- **Gone**: `DownloadLoop` (block 30), `SearchTaskRunner` (block 50), `SupervisedLoop` and `Work.run()` (block 60),
  `FakeShutdownDuringCycleDecisionReader` (block 30). Renamed: `LoopSupervisor` to `Supervisor`, `StatusLoop` to
  `StatusWatcher` (block 10), `DownloadCycle.run` to `run_once` (block 20), `SearchWorker.run_task(SearchTask)` to
  `search(keyword, channel=)` (block 50).
- **Not yet**: `ExpectedError`, a bug failing its turn alone, the 60 s after a bug, the time limits and
  `SupervisedWork` (lot 4b3); the bugs rule, `Supervisor.add` and the restarts (lots 4b4, 4b5).

## Accepted limits

- **A bug still stops the node** until lot 4b3, as on `main` (the spec's section 6, "During lot 4b2").
- **Source tracking's failed read waits a full `sources_interval`**, a fixed cadence (the spec's section 6, the
  operator on 2026-11-12).

## What was built, block by block

| # | PR | Branch | Block | Lines, files |
|---|---|---|---|---|
| 10 | #767 | `refactor/work-status-reading` | `Work`, `Supervisor`; the status reading the first work | 274, 17 |
| 20 | #769 | `refactor/download-round-run-once` | the download cycle's round renamed `run_once` | 92, 8 |
| 30 | #771 | `refactor/work-download-tracking` | download tracking a work, `DownloadLoop` removed | 497, 11 |
| 40 | #772 | `refactor/work-source-tracking` | source tracking a work of its own, reading the client's list | 478, 10 |
| 50 | #773 | `refactor/work-keyword-searches` | `BackoffSaver`; one work per client, channel and keyword, `SearchTaskRunner` removed | 467, 12 |
| 60 | #774 | `refactor/supervisor-drives-works` | the supervisor takes every work's turns, `Work.run()` removed | 279, 10 |
| 90 | | `docs/lot-4b2-wrap` | the holistic review's fixes, this handoff | 134, 18 |

No block passed a bound. Block 30 came under it at the second count (525 lines first): its wake tests were
parametrized and its helpers shortened; the closing block split them again into two named tests.

- **Departures, per block**:
  - **10**: the status loop is named `StatusWatcher`, not the draft's `StatusSensor`, to match `SourceWatcher` and
    because the glossary's `work` line refuses `loop`. `abc` added to `ast-grep/rules/application-imports.yml`.
    `test_a_refused_password_ends_the_loop` is now `test_a_refused_password_raises_out_of_the_turn`.
  - **20**: `architecture.md` section 7 names `DownloadCycle.run_once` (class 1: the draft left the old name).
  - **30**: `DownloadCycle` keeps its name. The loop's two shutdown tests moved to the supervisor's tests, where the
    draft deleted them. The test helper waiting for the wake is bounded at 1 s.
  - **40**: the builder `_source_watcher` stays in `test_source_watcher.py`. The two log lines that moved keep their
    text but are now written by the `source_watcher` module's logger, not `download_cycle`'s.
    `test_a_daemon_unreachable_at_the_start_reads_no_source` has no direct successor: the behaviour it held no longer
    exists, and the list-read test holds its intent. Class 1: `DownloadCycle.run_once`'s dead `return`.
  - **50**: the works are listed by `keyword_searches`, a function beside `KeywordSearch`, not inline in the
    composition as in the draft, so the enumeration test (a keyword listed twice, an empty one) runs on the code the
    node runs. The starvation test and `FakeNeverSuspendingSearchClient` are kept, where the draft removed them.
    `docs/migration-4x.md`'s sentence naming `search_task_runner`'s logger now names `backoff_saver`'s. Class 1:
    `search_worker.py`'s spec references, `download_cycle.py`'s "search tasks".
  - **60**: `test_work.py` deleted, its two tests moved to `test_supervisor.py`
    (`..._an_exception_in_a_turn_ends_the_run` now `..._ends_the_supervision`). The test "a loop that ends neither
    stops the others nor arms the bound" removed, as in the draft: the supervisor loops over each work's turns, so
    nothing it runs ends without raising. The supervisor's other tests renamed from loops to works and turns, every
    wait on a work's start bounded at 1 s. The search tests run their works under the real supervisor, stopped by a
    shutdown request at the end of the virtual time, in place of an `asyncio.timeout` around a bare task group. The
    lifecycle's `test_the_download_loop_shows_in_the_start` is now `test_download_enabled_shows_in_the_start`; its
    operator line `download enabled: download loop armed` is kept. `architecture.md` section 3's paragraph on loops
    is folded into the works' paragraph, and section 4 says the lifecycle hands the works to the supervisor.
  - **90**: the order of the works is a function of the composition, `works_in_start_order`, with its own test
    module, so the order has a test that needs no real socket (a wiring test would read the order in which parallel
    requests reach the fake aMule, which no one fixes). The raising turn's supervisor test is bounded at 1 s (class
    1: it hung when its code was stubbed). `testing.md`'s "c'est la **boucle**" and `architecture.md`'s "Le port-sync
    n'est pas une boucle du crawler" reworded beside the lines the review lists (class 1).
- **Left as is** (operator-facing or outside the lot's files): the log lines `download enabled: download loop armed`
  and `amuled unreachable at startup (...): tolerated, the loops retry`; `waker.py`'s docstring ("the in-process
  loops"); `docs/settings.md`'s "boucle de téléchargement", true for the operator; "download loop" in the docstrings
  and comments of files the lot does not otherwise touch (`FreeSpaceMeter`, `DownloadCandidate`, the tracked download
  store, two migrations, `test_cataloguer.py`, `test_migration_drop_verification.py`); the dated `agents/` documents.
- **Class 2 questions**: none in the lot.

## The holistic review's findings, and their exits

1 MAJOR, 12 MINOR; every one fixed in the closing block (the lead's choices, 2026-11-16).

| Finding | Exit |
|---|---|
| MAJOR: block 40's two behaviour tests never watched failing on their assertions | fixed: re-watched (The tests watched failing), the departure named |
| MINOR: blocks 10, 50, 60 watched failing on an import or a `TypeError`, then on mutations | fixed: re-watched, the departure named, block by block |
| block 30's compacted wake test, `_idle_cycle`'s silent clock, `wait_clock`'s comment | fixed: `test_a_wake_set_before_the_wait_ends_it_at_once_and_cancels_the_polls_sleep` and `test_a_wake_during_the_wait_ends_it_and_cancels_the_polls_sleep`, `_idle_cycle(wait_clock=...)`, the comment reworded |
| `run_once`'s "Never raises" | fixed: "absorbs an unavailable client and a store failure; a refused password or a bug leaves the turn" |
| code with no reader: the status watcher's `finally`, `_turn_taken` set first, their two tests | fixed: removed; they come back in lot 4b3 block 10 (Next step) |
| `test_..._lets_no_other_turn_start` claims more than the supervisor holds | fixed: renamed `test_a_shutdown_requested_during_a_turn_lets_that_work_take_no_further_turn`; the behaviour in Current state |
| the first requests' order | fixed: `works_in_start_order`, its test `test_crawler_composition_works_in_start_order.py` |
| the poll margin's false reason | fixed: a plain margin, in the docstring, `settings.md` and `architecture.md` |
| the glossary's `work, turn` line contradicts itself | fixed: its never column says "an asyncio `Task`" |
| "loop" and D18's words in the files listed | fixed: `architecture.md` (module table, run modes), `deploy.md`, `testing.md`, the blocking clock's message, three fake tests, `_RaisingWork`, `test_a_turn_that_raises_escapes_as_an_exception_group_without_arming_the_bound` |
| the `orchestration_integration` suite did not run | fixed: run, passed (Not validated) |
| the Kad probe, #774 blank | fixed: Next step; #774 in the table |
| #767's and #771's bodies | fixed with `gh pr edit`: #767 says a bug stops the node until lot 4b3; #771's table names the tests at the top of the stack |

## The tests watched failing

**Departure from strict TDD, blocks 10, 40, 50 and 60**: each wrote its tests first, but watched them fail only on a
missing module or a `TypeError` on a new constructor argument, then on mutations of the finished code. None of the
four pull requests named it. The closing block re-watched each behaviour test on its assertions: on the block's own
tip, its new code reduced to a stub with the parent's behaviour (an empty method, a wait that sleeps as `main` did),
the rest of `src` as the block left it, since the tests import its new names. Each run cleared `__pycache__` and
restored the tree after. Block 20 is a rename, and its failure (`AttributeError: 'DownloadCycle' object has no
attribute 'run_once'`) is the one a rename has; block 30 watched its wait tests fail on assertions over an empty wait.

| Block | Test | Stub | Failure |
|---|---|---|---|
| 10 | `test_each_turn_comes_after_its_wait_and_an_exception_in_a_turn_ends_the_run` | `Work.run()` returns at once | `Failed: DID NOT RAISE _LastTurnError` |
| 10 | `test_a_turn_that_never_suspends_still_lets_other_tasks_run_after_it` | the same | `AssertionError: assert [] == ['wait', 'turn']` |
| 10 | the status watcher's 11 alert and wait tests | an empty wait | `(0.0, RelayedLogLine(message='amuled kad: not connectable for 5 min', ...)) != (300.0, ...)`; `assert [] == [datetime.timedelta(seconds=40)]` |
| 10 | `test_the_next_reading_waits_what_is_left_of_the_minute_since_the_latest_one_ended` | a full minute after each reading, `main`'s sleep | `At index 0 diff: datetime.timedelta(seconds=60) != datetime.timedelta(seconds=40)` |
| 10 | `test_a_minute_already_past_the_latest_reading_starts_the_next_at_once` | the same | `Left contains one more item: datetime.timedelta(seconds=60)` |
| 40 | `test_turns_start_the_interval_apart_whatever_each_one_lasts` | `main`'s cadence: the interval from the end of the latest turn, a failed listing stamping nothing | `At index 1 diff: datetime.datetime(2026, 6, 12, 0, 5, 1, ...) != datetime.datetime(2026, 6, 12, 0, 5, ...)` |
| 40 | `test_a_failed_read_is_tried_again_a_full_interval_after_it_started[listing-the-downloads]` | the same | `At index 0 diff: datetime.datetime(2026, 6, 12, 0, 0, ...) != datetime.datetime(2026, 6, 12, 0, 5, ...)` |
| 40 | `test_a_failed_read_is_tried_again_a_full_interval_after_it_started[reading-the-sources]` | the same | `At index 0 diff: datetime.datetime(2026, 6, 12, 0, 5, 1, ...) != datetime.datetime(2026, 6, 12, 0, 5, ...)` |
| 40 | `test_a_turn_that_raised_still_waits_the_interval_from_its_start` | the same | `assert [] == [datetime.timedelta(seconds=300)]` |
| 50 | `test_each_channel_and_keyword_searches_in_its_own_task` | `KeywordSearch`'s wait empty, its turn the search alone, `keyword_searches` without the dedupe, `BackoffSaver.saving()` a bare `yield` | `At index 0 diff: (0.0, '', 'x') != (0.0, 'keroro', 'x')` |
| 50 | `test_a_failed_channel_sleeps_until_its_backoff_ends` | the same | `assert [0.0, 0.0, 30.0, 60.0, 90.0] == [0.0, 60.0, 90.0]` |
| 50 | `test_an_unreachable_client_sleeps_until_its_backoff_ends` | the same | `assert [0.0, 0.0, 0.....0, 60.0, ...] == [0.0, 60.0, 60.0, 90.0, 90.0]` |
| 50 | `test_a_search_woken_from_its_wait_waits_again_for_a_backoff_set_meanwhile` | the same | `At index 1 diff: (0.0, 'kad') != (60.0, 'kad')` |
| 50 | `test_a_backoff_the_previous_run_saved_delays_the_first_search` | the same | `assert [0.0, 30.0, 60.0, 90.0] == [40.0, 70.0]` |
| 50 | `test_the_backoff_is_saved_at_each_change`, and the saver's `test_a_search_that_changed_the_backoff_saves_it_and_one_that_did_not_saves_nothing` | the same | `assert [] == [{BackoffKey(...kad')}, set()]` |
| 50 | `test_a_refused_save_is_logged_and_tried_again_after_the_next_search` | the same | `assert [] == [LoggedLine(l...next search')]` |
| 50 | `test_the_backoff_resumed_at_the_start_is_not_saved_again` | the reference copy taken at construction | `Left contains one more item: {BackoffKey(client_name='amuled', channel='ed2k'): BackoffState(attempts=1, ...)}` |
| 60 | `test_a_turn_that_never_suspends_still_lets_other_tasks_run_after_it` | `Supervisor._take_turns` returns at once | `AssertionError: assert [] == ['wait', 'turn']` |
| 60 | the six search tests under the supervisor | the same | `assert [] == [0.0, 60.0, 90.0]`, `assert [] == [40.0, 70.0]`, the same for each |
| 60 | `test_each_turn_comes_after_its_wait_and_an_exception_in_a_turn_ends_the_supervision`, `test_a_turn_that_raises_escapes_...` | the same | `Failed: Raised exception group did not match: TimeoutError() is not an exception group`, at the 1 s bound |
| 60 | the stop tests, `test_a_shutdown_requested_during_a_turn_lets_that_work_take_no_further_turn`, the four lifecycle tests | the same | `TimeoutError` at the 1 s bound on a work's start |

- **The tests that cannot fail on an assertion before their code exists**: block 60's, where the first thing a test
  observes is a turn. With no turn, a test waiting for one fails at its 1 s bound, never on its assertion; the stop
  tests hold the arming and the cancellation, which the parent's supervisor already had, and block 30 watched them
  fail on a dropped `task.cancel()`.
- **Passing on the stubs, as they must**: `test_channels_do_not_wait_for_each_other` and the starvation test (block
  50: they hold `Work.run()`'s yield, block 10's); `test_a_shutdown_requested_before_the_start_starts_no_turn` (block
  60: no turn starts either way); `test_the_backoff_resumed_at_the_start_is_not_saved_again` on the bare `yield` (an
  empty saver saves nothing), hence its own stub above.
- **Block 40 on the review's stub too** (an empty wait, `run_once` with `main`'s gate on the interval since the latest
  read started): 9 failed, the three behaviour cases among them (`Right contains 2 more items`; `At index 0 diff:
  datetime.datetime(2026, 6, 12, 0, 0, ...) != ...(0, 5, ...)`; `assert [] == [datetime.datetime(2026, 6, 12, 0, 5,
  ...)]`), the five others failing because an empty wait spaces nothing.
- **The closing block's own**: `test_crawler_composition_works_in_start_order.py`'s two tests, over the lot's order
  `[*searches, status_watcher, *tracking]`: `At index 0 diff: 'ed2k keroro' != 'status'`, `At index 0 diff: 'kad
  keroro' != 'status'`.
- **Removed with their code**: block 10's `test_a_reading_that_raised_waits_a_full_minute_before_the_next` and block
  30's `test_after_a_turn_that_raised_the_next_waits_the_poll_interval_too`.
- **Block 60's arming moved after the `cancel()` calls is an equivalent mutation**: every test passes, since a
  cancellation only reaches a work at its next suspension, after the arming either way.

## Section 4's rows, where each is held

| Row | Test |
|---|---|
| The behaviour tests of the status reading, download tracking, source tracking and the searches, moved, none removed | the moves: block 10 (`test_status_loop.py` to `test_status_watcher.py`), block 30 (#771's table), block 40 (#772's table), block 50 (#773's table), block 60 (`test_work.py` to `test_supervisor.py`). Two tests have no successor, their behaviour gone, both accepted by the holistic review: block 40's `test_a_daemon_unreachable_at_the_start_reads_no_source` (held in intent by `test_a_client_unavailable_listing_its_downloads_reads_no_source`) and block 60's "a loop that ends" (`_take_turns` is `while True`) |
| A channel backed off when the node restarts | `test_keyword_search.py::test_a_backoff_the_previous_run_saved_delays_the_first_search`; through the real composition, `test_crawler_composition_wiring.py::test_a_backoff_the_previous_run_saved_holds_the_ed2k_search`; the resume before the works, `test_crawler_lifecycle.py::test_the_backoff_waits_the_previous_run_saved_are_resumed_before_the_works` |
| A shutdown during any turn | `test_supervisor.py::test_a_stop_without_a_signal_arms_the_bound_before_cancelling_every_work`, `::test_a_shutdown_requested_during_a_turn_lets_that_work_take_no_further_turn`, `::test_a_shutdown_requested_before_the_start_starts_no_turn`; a wait cancelled, `test_download_cycle.py::test_a_wait_cancelled_at_the_shutdown_raises_and_leaves_no_task`; the bound itself, `test_crawler_composition_shutdown_bound.py` and `test_crawler_composition_wiring.py::test_the_shutdown_deadline_spares_the_run_then_cuts_a_logout_amuled_never_answers`; against a real amuled, `test_crawler_loop.py::test_real_loop_runs_one_search_and_stops` |
| A failed source list read | `test_source_watcher.py::test_a_failed_read_is_tried_again_a_full_interval_after_it_started`, the list read and the sources read |

## What must not change

| Check | Result |
|---|---|
| The matching decisions on the real catalog | **not run**: the umbrella's comparison (`agents/reference/2026-11-04-v5-audit-instruments/matching/`) reads the operator's `catalog.db` in `/home/geoffrey/Projets/mulewatch/data`, outside the repository. The lot touches no matching code: `git diff --name-only origin/main...HEAD -- packages/crawler/src/p2pwatch/domain/matching packages/crawler/src/p2pwatch/adapters/driven/config` lists nothing (2026-11-16), and the gate's golden corpus passes |
| `deploy/matcher.yml` and its keys | `git diff --stat origin/main...HEAD -- deploy/matcher.yml deploy/targets.yml` empty; `validate-config` on `deploy/`, `AMULE_API_PASSWORD` set to a placeholder: `Config valid` (2026-11-16) |
| A healthy node's notifications, a channel's search cadence | at the release candidate |

## The lot's counts

- Fix-backs: 0. Cascaded rebases: 0.
- Runs re-triggered: 0 so far.
- Bodies the operator called unreadable: 0.

## For lot 7 (the operator pages)

- Source tracking runs start to start, and a failed read waits a full `sources_interval` (`docs/settings.md` says
  so since block 40).
- Source tracking's two log lines come from the `source_watcher` module's logger, the backoff's "not saved" line
  from `backoff_saver`'s (`docs/migration-4x.md` corrected in block 50).
- While aMule is unreachable, source tracking writes one `sources skipped` warning every `sources_interval`, beside
  download tracking's: it lists the client's downloads itself.
- Nothing else an operator sees changed.

## Pitfalls learned

- **A test awaiting a work's start hangs rather than fails when the work never starts**: every such wait is bounded
  (`asyncio.wait_for(work.started.wait(), 1.0)`), as the first stack's block 38 learned (blocks 30, 60). The raising
  turn's test had no bound and hung on the closing block's stub; the search starvation test still has none (its
  loop waits for 100 calls): run a stub or a mutation of the supervisor under `timeout`.
- **A mutation removing the yield after a turn hangs the tests whose work never suspends**
  (`test_a_shutdown_requested_during_a_turn_lets_that_work_take_no_further_turn`, the search starvation test): the
  loop is starved, so no `wait_for` can fire. Run mutations under `timeout`, and those tests alone (blocks 30, 60).
- **A constructor argument added hides every behaviour failure behind a `TypeError`** (blocks 40, 50, 60, as lot
  4b1's blocks 40 and 50): watch the behaviour fail on a stub of the new code, the argument in place, before writing
  the code.
- **A mutation reverted within the second leaves a stale `.pyc`**: clear `__pycache__` under `src` after each one
  (blocks 30 to 60).
- **Serena's renames**: block 20's `rename_symbol` missed a double-backticked name in a docstring; block 10 renamed
  through `git mv` and a word-bounded `perl`, since Serena's index was stale and would have rewritten
  `agents/reference/`'s dated probe. A `\b` rename skips an underscore-prefixed attribute (`self._loop_supervisor`):
  check with `git grep -w`.
- **Two works now list the client's downloads**: a wiring test counting listings no longer counts download rounds
  (block 40's disk wiring test waits for 3).
- **The order of parallel first requests is not a wiring test's to read**: each work's first request leaves on its
  own connection, and the fake aMule's threads record them in the order they are served (closing block).
- **`pkill -f <pattern>` kills the shell running it** when the pattern matches its own command line (block 30).
- **In zsh, an unquoted `$files` does not word-split**: use `xargs -0` (block 10).
- **`collections.abc.Callable` is refused in tests too** (`TID251`): a callback is a `Protocol` (block 60).

## Not validated

- Nothing ran against a real node; the works run on fake clocks or the virtual-time loop.
- **The `orchestration_integration` suite passed** against a real amuled on 2026-11-16, at the closing block's code
  (`ade4f67f`): `test_real_loop_runs_one_search_and_stops`, 1 passed. The daemon was `p2pwatch-amule:dev`, built from
  the tree (`docker build -f packages/amule/Dockerfile`), published on `-p 14711:4711`, the suite run with
  `P2PWATCH_TEST_API_HOST=127.0.0.1 P2PWATCH_TEST_API_PORT=14711`. `api_integration` and `download_integration` did
  not run: no adapter changed.
- Block 50's first commit (`7b7c875d`, the saver under the runner) was not gated alone, only the block's tip.
- The first requests' order and source tracking's cadence on a real node.
- The matching comparison on the real catalog (What must not change).

## Next step

The operator reads and merges the stack, rebased onto `main` if it moved. No release: v5 ships after lots 4c to 7 and
their release candidates. `BACKLOG.md`'s sub-entry 4b stays open until lot 4b5; the lot adds nothing to it.

Then lot 4b3, a bug fails its turn alone (the spec's section 5 and appendix A, "Lot 4b3"): `ExpectedError`, the
supervisor's three ends of a turn and 60 s after a bug, a failed search raised, a request to aMule bounded at 60 s,
each client's latest search starts kept in `local.db`, and each work's time limit with the notifications shielded.
It is its own stack from `main`, once lot 4b2 has merged. Its block 10, which brings the turn that survives a bug,
also brings back, with their first reader (D8, "the later of that and the work's own wait"):

- the status watcher's stamp of a reading that raised, and its test (`test_a_reading_that_raised_waits_a_full_minute_before_the_next`, removed here);
- download tracking's wait after a round that raised, and its test
  (`test_after_a_turn_that_raised_the_next_waits_the_poll_interval_too`, removed here).

Lot 4b3's acceptance row "Kad bug" (appendix B) takes the probe
`agents/reference/2026-11-04-v5-audit-instruments/fault-isolation/test_fault_isolation.py::test_a_kad_bug_stops_the_working_ed2k_tasks_too`
"inverted and moved into the package's tests". The probe imports `LoopSupervisor`, `SearchTaskRunner` and
`StatusLoop`, which this lot removed, so it can no longer be inverted: lot 4b3 block 10 rewrites it over `Supervisor`
and `keyword_searches`, keeping what it shows (a bug in the Kad search, the eD2k searches that must go on).

# Handoff: v5 lot 4b2, the supervisor (tier Spec)

Drafted by block 60's teammate from the block reports (#767, #769, #771, #772, #773, the collapsed "Block report" of
each pull request body) and its own. To be corrected by the closing block, which also fixes the holistic review's
findings. Spec: `agents/specs/2026-11-15-v5-lot-4b-health-model.md`, lot 4b2 of its five lots (D19), decisions D7,
D17, D18.

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
- **The works, as the composition lists them**:

  | Work | Module | Its wait |
  |---|---|---|
  | one per client, channel and keyword, listed by `keyword_searches` | `keyword_search.py` (`KeywordSearch`) | until neither its client nor its channel is backed off, checked again after each sleep; a backoff the previous run saved delays the first search |
  | the status reading | `status_watcher.py` (`StatusWatcher`) | what is left of the minute since the latest reading ended, nothing before the first |
  | download tracking | `download_cycle.py` (`DownloadCycle`) | nothing before the first turn, then `download.poll_interval_seconds` or a download decision's wake, the first to come |
  | source tracking | `source_watcher.py` (`SourceWatcher`) | what is left of `download.sources_interval_seconds` since the previous turn started, nothing before the first |

  The two download works exist only on a node with `download:`. Each lists the client's downloads itself.
- **`BackoffSaver`** (`backoff_saver.py`), one for every search, sets the shared backoff in `local.db` after each
  turn that changed it. It takes its reference copy at the first search, since it is built before the lifecycle
  resumes the saved backoff. A refused save is logged and tried again after the next search, as on `main`.
- **`CrawlerLifecycle`** takes the works and hands them to the supervisor once the backoff is resumed, the node
  announced and the catalog re-evaluated.
- **Source tracking changed in two ways** (block 40, the operator's choice of 2026-11-12, written in
  `docs/settings.md`): its turns run `sources_interval` apart from start to start, where they waited the interval
  after each download round; the start is stamped before the read, so a failed read waits a full interval, where it
  was tried again one poll later. Nothing else changed in behaviour.
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
| 60 | | `refactor/supervisor-drives-works` | the supervisor takes every work's turns, `Work.run()` removed | 279, 10 |
| 90 | | `docs/lot-4b2-wrap` | closing block | |

No block passed a bound. Block 30 came under it at the second count (525 lines first): its wake tests were
parametrized and its helpers shortened.

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
    nothing it runs ends without raising. The supervisor's other tests renamed from loops to works and turns (`a
    failing loop` is now `a crashing turn`), every wait on a work's start bounded at 1 s. The search tests run their
    works under the real supervisor, stopped by a shutdown request at the end of the virtual time, in place of an
    `asyncio.timeout` around a bare task group. The lifecycle's `test_the_download_loop_shows_in_the_start` is now
    `test_download_enabled_shows_in_the_start`; its operator line `download enabled: download loop armed` is kept.
    `architecture.md` section 3's paragraph on loops ("Chaque boucle est une itération suivie d'un sommeil") is
    folded into the works' paragraph, and section 4 says the lifecycle hands the works to the supervisor.
- **Left as is** (operator-facing or outside the lot's files): the log lines `download enabled: download loop armed`
  and `amuled unreachable at startup (...): tolerated, the loops retry`; `waker.py`'s docstring ("the in-process
  loops"); `docs/settings.md`'s "boucle de téléchargement", true for the operator; the dated `agents/` documents.
- **Class 2 questions**: none in the lot.

## The tests watched failing

One line per new or moved behaviour; the block reports hold every case. "Test first" means the test ran over the code
before the block; "mutation" means it ran over the finished code, one change at a time, `__pycache__` cleared after.

| Block | Test | How | Failure |
|---|---|---|---|
| 10 | `test_work.py` | test first | `ModuleNotFoundError: No module named 'p2pwatch.application.steps.work'` |
| 10 | the status watcher's alert tests, its wait written empty | test first | `(0.0, RelayedLogLine(message='amuled kad: not connectable for 5 min', ...)) != (300.0, ...)` |
| 10 | the yield after a turn | mutation | `assert ['wait', 'tur...wait', 'turn'] == ['wait', 'turn']` |
| 10 | a minute already past starts the next at once | mutation | `assert [datetime.tim...econds=86370)] == []` |
| 20 | the renamed round | test first | `AttributeError: 'DownloadCycle' object has no attribute 'run_once'` |
| 30 | the cycle's wait, written empty | test first | `assert [] == [datetime.tim...a(seconds=30)]`; `assert [] == [<WakeSubject.DOWNLOAD: 1>]` |
| 30 | the first turn at once | mutation | `TimeoutError` |
| 30 | the losing task cancelled | mutation | `assert {<Task pending ... FakeBlockingMonotonicClock.sleep() ...>} == set()` |
| 30 | the supervisor's two shutdown tests | mutation (`task.cancel()` dropped) | `TimeoutError` |
| 40 | source tracking's own list read | test first | `TypeError: SourceWatcher.__init__() got an unexpected keyword argument 'download_client'` |
| 40 | start to start | mutation (the end stamped) | `At index 1 diff: datetime.datetime(2026, 6, 12, 0, 5, 1, ...) != datetime.datetime(2026, 6, 12, 0, 5, ...)` |
| 40 | a failed read waits a full interval | mutation (only a turn that worked stamped) | `At index 0 diff: datetime.datetime(2026, 6, 12, 0, 0, ...) != datetime.datetime(2026, 6, 12, 0, 5, ...)` |
| 40 | a refused read ends the turn | mutation | `ReadRejectedError: amuled_rejected` |
| 50 | `BackoffSaver` | test first | `ModuleNotFoundError: No module named 'p2pwatch.application.steps.backoff_saver'` |
| 50 | the reference copy at the first search | mutation | `Left contains one more item: {BackoffKey(client_name='amuled', channel='ed2k'): BackoffState(attempts=1, ...)}` |
| 50 | the wait checked again after each sleep | mutation (`if` for `while`) | `assert [(0.0, 'ed2k'... 'ed2k'), ...] == [(0.0, 'ed2k'...180.0, 'kad')]` |
| 50 | a saved backoff delays the first search | mutation (no wait) | `assert [0.0, 30.0, 60.0, 90.0] == [40.0, 70.0]` |
| 60 | the supervisor's tests over works | test first | `TypeError: '_CountedWork' object is not callable`, the same for each test double |
| 60 | the lifecycle over works | test first | `TypeError: CrawlerLifecycle.__init__() got an unexpected keyword argument 'works'` |
| 60 | the search tests under the supervisor | test first | `TypeError: 'KeywordSearch' object is not callable` |
| 60 | the yield after a turn, in the supervisor | mutation | `assert ['wait', 'tur...wait', 'turn'] == ['wait', 'turn']`, and the search starvation test |
| 60 | the wait before the turn | mutation (swapped) | `At index 0 diff: 'turn' != 'wait'` |
| 60 | the bound armed at the stop | mutation (never armed) | `assert 'search cancelled' == 'armed'`, and two lifecycle tests |
| 60 | every work cancelled at the stop | mutation (`task.cancel()` dropped) | `TimeoutError` at each stop test's 1 s bound |

- **Block 60's arming moved after the `cancel()` calls is an equivalent mutation**: every test passes, since a
  cancellation only reaches a work at its next suspension, after the arming either way.
- **Block 60's `test_..._starts_no_turn` and `test_..._lets_no_other_turn_start` were not watched failing in this
  lot**: they hold behaviour `main` already had, and block 30 watched them fail on a dropped `task.cancel()`.

## Section 4's rows, where each is held

| Row | Test |
|---|---|
| The behaviour tests of the status reading, download tracking, source tracking and the searches, moved, none removed | the moves: block 10 (`test_status_loop.py` to `test_status_watcher.py`), block 30 (#771's table), block 40 (#772's table), block 50 (#773's table), block 60 (`test_work.py` to `test_supervisor.py`). Two tests have no successor, their behaviour gone: block 40's `test_a_daemon_unreachable_at_the_start_reads_no_source` and block 60's "a loop that ends" (the closing block's review to judge) |
| A channel backed off when the node restarts | `test_keyword_search.py::test_a_backoff_the_previous_run_saved_delays_the_first_search`; through the real composition, `test_crawler_composition_wiring.py::test_a_backoff_the_previous_run_saved_holds_the_ed2k_search`; the resume before the works, `test_crawler_lifecycle.py::test_the_backoff_waits_the_previous_run_saved_are_resumed_before_the_works` |
| A shutdown during any turn | `test_supervisor.py::test_a_stop_without_a_signal_arms_the_bound_before_cancelling_every_work`, `::test_a_shutdown_requested_during_a_turn_lets_no_other_turn_start`, `::test_a_shutdown_requested_before_the_start_starts_no_turn`; a wait cancelled, `test_download_cycle.py::test_a_wait_cancelled_at_the_shutdown_raises_and_leaves_no_task`; the bound itself, `test_crawler_composition_shutdown_bound.py` and `test_crawler_composition_wiring.py::test_the_shutdown_deadline_spares_the_run_then_cuts_a_logout_amuled_never_answers` |
| A failed source list read | `test_source_watcher.py::test_a_failed_read_is_tried_again_a_full_interval_after_it_started`, the list read and the sources read |

## What must not change

| Check | Result |
|---|---|
| The matching decisions on the real catalog | for the closing block. The lot touches no matching code |
| `deploy/matcher.yml` and its keys | for the closing block (`git diff --stat origin/main -- deploy/matcher.yml deploy/targets.yml`, `validate-config` on `deploy/`) |
| A healthy node's notifications, a channel's search cadence | at the release candidate |

## The lot's counts

For the closing block: fix-backs, cascaded rebases, runs re-triggered, bodies the operator called unreadable.

## For lot 7 (the operator pages)

- Source tracking runs start to start, and a failed read waits a full `sources_interval` (`docs/settings.md` says
  so since block 40).
- Source tracking's two log lines come from the `source_watcher` module's logger, the backoff's "not saved" line
  from `backoff_saver`'s (`docs/migration-4x.md` corrected in block 50).
- Nothing else an operator sees changed.

## Pitfalls learned

- **A test awaiting a work's start hangs rather than fails when the work never starts**: every such wait is bounded
  (`asyncio.wait_for(work.started.wait(), 1.0)`), as the first stack's block 38 learned (blocks 30, 60).
- **A mutation removing the yield after a turn hangs the tests whose work never suspends**
  (`test_a_shutdown_requested_during_a_turn_lets_no_other_turn_start`, the search starvation test): the loop is
  starved, so no `wait_for` can fire. Run mutations under `timeout`, and those tests alone (blocks 30, 60).
- **A mutation reverted within the second leaves a stale `.pyc`**: clear `__pycache__` under `src` after each one
  (blocks 30 to 60).
- **Serena's renames**: block 20's `rename_symbol` missed a double-backticked name in a docstring; block 10 renamed
  through `git mv` and a word-bounded `perl`, since Serena's index was stale and would have rewritten
  `agents/reference/`'s dated probe. A `\b` rename skips an underscore-prefixed attribute (`self._loop_supervisor`):
  check with `git grep -w`.
- **Two works now list the client's downloads**: a wiring test counting listings no longer counts download rounds
  (block 40's disk wiring test waits for 3).
- **`pkill -f <pattern>` kills the shell running it** when the pattern matches its own command line (block 30).
- **In zsh, an unquoted `$files` does not word-split**: use `xargs -0` (block 10).
- **`collections.abc.Callable` is refused in tests too** (`TID251`): a callback is a `Protocol` (block 60).

## Not validated

- Nothing ran against a real node or a real aMule; the works run on fake clocks or the virtual-time loop.
- No Docker integration suite ran in this lot: no adapter changed.
- Block 50's first commit (`7b7c875d`, the saver under the runner) was not gated alone, only the block's tip.
- The first search's order against the first status reading on a real node; source tracking's cadence on a real node.
- The matching comparison on the real catalog (What must not change).

## Left for the closing block

The holistic review over `git diff origin/main...origin/refactor/supervisor-drives-works` and its findings' exits;
the matching comparison and `validate-config`; the lot's counts; this handoff corrected; `BACKLOG.md` reconciled
(the sub-entry 4b stays open until lot 4b5).

## Next step

The operator reads and merges the stack, rebased onto `main` if it moved. No release: v5 ships after lots 4c to 7 and
their release candidates.

Then lot 4b3, a bug fails its turn alone (the spec's section 5 and appendix A, "Lot 4b3"): `ExpectedError`, the
supervisor's three ends of a turn and 60 s after a bug, a failed search raised, a request to aMule bounded at 60 s,
each client's latest search starts kept in `local.db`, and each work's time limit with the notifications shielded.
It is its own stack from `main`, once lot 4b2 has merged.

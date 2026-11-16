# Handoff: v5 lot 4b3, a bug fails its turn alone (tier Spec)

Drafted by block 55's teammate from the block reports (#776, #777, #779, #780, #781, the collapsed "Block report" of
each pull request body) and its own. Corrected by the closing block, which also fixed the holistic review's findings
(`.reviews/v5-lot4b3-holistic.md`, below). Spec:
`agents/specs/2026-11-15-v5-lot-4b-health-model.md`, lot 4b3 of its five lots (D19), decisions D8 to D13, D16, D17,
D18.

## Current state

- **A turn ends in one of three ways** (`application/steps/supervisor.py`), told apart by the exception's type alone:
  it worked; it raised an `ExpectedError`, logged in one warning line `<work>: <error>`; or it raised anything else, a
  bug, logged with its trace as `bug in <work>`, the exception it was raised from kept in that trace. Either failure
  fails that turn alone: every other work goes on.
- **`ExpectedError`** (`domain/expected_error.py`) is the base of every error a driven port declares: `ClientError`
  (`ClientAuthError`, `ClientUnreachableError`, `SearchFailedError` among them), `StoreError`,
  `InaccessiblePathError`, `CatalogCopyError`. A test lists them by hand
  (`test_every_error_a_driven_port_declares_is_an_expected_error`), so a new port's error must be added there.
- **After a bug, the work's next turn waits the later of 60 s (`WAIT_AFTER_A_BUG`) and its own wait**, never their
  sum. An expected error adds no wait: each work already paces itself.
- **A wait that raises still ends the node**, as on `main`: waits are clock arithmetic outside the turn
  (`test_a_wait_that_raises_escapes_as_an_exception_group_without_arming_the_bound`).
- **Each work names itself** in these lines as its component does: `status reading amuled`, `download tracking
  amuled`, `source tracking amuled`, `search 'keroro' amuled kad`.
- **A turn that raised stamps again**: the status watcher spaces its next reading a full minute after one that raised,
  download tracking waits its poll after a round that raised (the `finally` lot 4b2 removed). Without them a refused
  password would retry the login at full speed.
- **A refused password while the node runs** fails each status reading and each search as an expected error; the node
  runs on. Its own alert is lot 4c's.
- **A failed search raises** `SearchFailedError` or `ClientUnreachableError` once its backoff is set, its warning
  logged and its event dispatched; `BackoffSaver.saving()` saves in a `finally`, a cancelled search included. A
  failed search is logged twice: by the search worker (with its backoff, `backoff <seconds> s`) and by the supervisor.
- **A request to aMule lasts 60 s at most in all** (`_send`, the adapter's module function, under `asyncio.timeout`,
  the bound a constant of the composition passed to the adapter, which declares it as `AmuleApiClient.request_bound`),
  six times httpx's 10 s per phase; past it, a `ClientUnreachableError`. The login, the one re-login a 401 allows, the
  retried call and the logout are each bounded on their own.
- **A login cancelled in flight closes its httpx client** (`_connect`, `except BaseException`): a time limit or the
  shutdown cutting a turn in its login no longer leaves the client and its sockets open.
- **Each client's latest search starts are kept in `local.db`**, table `latest_search_starts` (client name, channel,
  scope, instant in micros; the first three its key), schema version 16. `SearchStartWriter` / `SearchStartReader`,
  implemented by `SqliteSearchStartStore`, their contract run by it and by `FakeSearchStartStore`. The adapter writes
  a start as it reserves it (eD2k under its lock, a Kad slot converted to the wall clock) and reads them once when it
  is built, each through `remaining_wait`. A store failure is logged: on the read the client starts without them, on
  the write the search goes on.
- **Each work has a time limit** (`SupervisedWork`, its limits derived by `composition/work_time_limits.py`'s
  `AmuleWorkTimeLimits`): the sum of the bounds on its turn's path plus `TIME_LIMIT_MARGIN`, 5 minutes. The supervisor
  races the turn against `MonotonicClock.sleep(limit)` in a `TaskGroup`, in the task that waited for the turn; a turn
  still running is cut, logged `<work>: past its time limit of <seconds> s` without a trace, and counted as a bug
  (`TurnTimeoutError`). The turn's own exception is kept out of the race's task group, so only the expiry's is
  unwrapped. The yield after each turn is gone: the race always suspends at its end. The composition logs each work's
  limit at debug level as it hands them to the lifecycle (`<work>: time limit <seconds> s`), the request bound read
  from the client.
- **A notification already decided is sent even when its turn is cut** (D16): the file judge, after a decision's
  write, and the download tracker, after a completion's, send through `ObservabilityDispatcher.dispatch_shielded`, a
  task of its own under `asyncio.shield`, which the dispatcher holds to its end. `shield` joins the core's asyncio
  names (`ast-grep/rules/core-import-names.yml`). At the shutdown, the lifecycle waits for the sends the cancelled
  turns left (`finish_shielded_dispatches`), each within its notification timeout, inside the armed shutdown deadline,
  before the resources close. A bug in a send whose turn was cut is logged `bug in the notification of <event>` with
  its trace, through the dispatcher's logger.
- **Not yet**: the bugs rule and recording the turns on the components (lot 4b4 block 10), "searches failed" and
  "connected to no network" (4b4 block 20), the restarts (4b4, 4b5).

## Accepted limits

The spec's section 6, those this lot reaches:

- **An intermittent bug** never turns a rule failing (there is no bugs rule yet); its trace is in the log each time.
- **No static proof of which errors are expected**: the listing test is written by hand.
- **A notification is lost if the process dies between a decision's write and its send**, as today; a send still in
  flight when the shutdown deadline fires is cut with the rest.
- **From lot 4b3 to lot 4c, a password refused while the node runs alerts nothing**: an expected error each turn, a
  line in the log.
- **A turn that grows past its limit's 5 minutes of margin is cut as a bug**: the download works grow with the
  tracked downloads and their sources, a search with the files of its answer.

## What was built, block by block

| # | PR | Branch | Block | Lines, files |
|---|---|---|---|---|
| 10 | #776 | `feat/turn-ends-expected-or-bug` | `ExpectedError`; a bug fails its turn alone, 60 s before the next | 546, 31, accepted |
| 20 | #777 | `feat/search-errors-raised` | a failed search raised once its backoff is saved | 105, 7 |
| 30 | #779 | `fix/amuleapi-request-total-bound` | a request to aMule bounded at 60 s | 95, 10 |
| 40 | #780 | `feat/search-starts-kept` | each client's latest search starts kept in `local.db` | 934, 25, accepted |
| 50 | #781 | `feat/turn-time-limit` | each work's time limit | 459, 13 |
| 55 | #782 | `feat/notifications-shielded` | a decision's or a completion's notification sent even when its turn is cut | 154, 10 |
| 90 | | `docs/lot-4b3-wrap` | the holistic review's fixes, this handoff | 479, 25: split in two, below |

- **Past a bound, accepted by the operator**: block 10 past both, the files on 2026-11-11 (the spec's row: each
  port's error re-based is one line in each of its files) and the lines on 2026-11-16 ("A": the three ways a turn
  ends cannot come without their acceptance tests). Block 40 past both, accepted on 2026-11-12 (the spec's row); it
  grew to 934 lines past the 841 of its draft (the tests written out, not compacted, four tests added), which the
  operator accepted past both bounds.
- **Block 55 split out of block 50**, as the spec's row foresees: with the shield, block 50 would have been about 570
  lines and 21 files (the lead, 2026-11-16).
- **The closing block passed the file bound** (479 lines, 25 files, 2026-11-16): its commits split after the comments'
  rewording, 378 lines and 18 files from block 55 to it (the review's code fixes), then 101 lines and 10 files (the
  guard of `of_search`, the names, the composition's limits read by a wiring test), this handoff and the spec's
  corrections on top. Each part's tip passed the gate; the lead cuts the branches.
- **Departures, per block**:
  - **10**: `ExpectedError` re-bases the errors of the **driven** ports only (the operator, 2026-11-11, "every failure
    a driven port declares"); the driving ports' errors (`MergeError`, `InvalidConfigError`, `OutOfSpaceError`,
    `ShutdownDeadlineError`) go to the command line, never into a turn, where D9 says "a port of the core". A wait
    that raises still ends the node (D8 speaks of the turn). The 60 s is `WAIT_AFTER_A_BUG` (the draft's
    `FLOOR_AFTER_A_BUG` dropped). `DownloadCycle` and `SourceWatcher` take `client_name`, to name themselves as their
    component does; `SearchWorker.client_name` added. `FakeTimedSearchClient`'s broken keyword or channel meets its
    bug at the end of its search's duration, not at once, so a stub without the 60 s does not spin the virtual-time
    loop at time 0. The Kad probe is rewritten over `Supervisor` and `keyword_searches` as
    `test_a_bug_on_every_kad_search_leaves_the_ed2k_searches_going_on`; the dated probe in `agents/reference/` is
    untouched. The two tests lot 4b2 removed are back, `test_after_a_turn_that_raised_the_next_waits_the_poll_interval_too`
    over a refused password rather than a bug. Class 1: the glossary's `inaccessible path` line ("the declared
    failure" now "the expected error"), `architecture.md` §10's "crashe bruyamment" and §11's "laisser crasher".
  - **20**: none from the spec. From the draft #730: the saver's cancelled case tested; the raise tested end to end
    under the supervisor; the draft's docstring citing "spec v5 lot 4, D2" not taken. `architecture.md` section 5's
    resilience bullet.
  - **30**: none from the spec. From the draft #733: the test waits for the call with `asyncio.wait(timeout=2.0)` and
    asserts it finished, so a missing bound fails on an assertion; it matches the bound's own message (`no whole
    answer within 0.5 s`), so a phase timeout cannot pass it; the trickling server sleeps through
    `AsyncioMonotonicClock`.
  - **40**: appendix B's row runs both channels over two keywords sharing the Kad word `keroro` (`keroro`, `keroro
    mission`). From the draft #734: four tests added (a start stored an hour ahead waits one spacing at most; Kad's
    second slot written as its own instant; the wiring test reads back the Kad start the run wrote; a keyword without
    a Kad word still waits a spacing); the names `_next_start_by_scope`, `_next_starts_from`, `scope_key`.
    `architecture.md`: schema version 16, the table, the spacing kept across a restart.
  - **50**: appendix B's "Time limit" row names `FakeBlockingMonotonicClock`; the hung-turn test runs on the
    virtual-time loop over `FakeLoopMonotonicClock`, since a blocking clock's sleep never ends and no limit could
    pass. The shield moved to block 55. From the draft #735: `AmuleWorkTimeLimits` in `work_time_limits.py` and
    `TIME_LIMIT_MARGIN` (the draft's `AmuleTurnTimeLimits`, `turn_time_limits.py`, `TIME_LIMIT_ALLOWANCE`);
    `keyword_searches` takes a `time_limit_of` callback (`SearchTimeLimit`) and returns `SupervisedWork`s;
    `works_in_start_order` generic; the draft's "a turn ending within its limit keeps its outcome" test not kept (the
    existing end-of-turn tests hold it, shown by a mutation). The adapter publishes `ED2K`, `KAD`, `START_SPACING`,
    `kad_word_of`.
  - **90**: the composition's limits read through a debug line it writes per work, and `AmuleWorkTimeLimits` given the
    bound the client declares (`AmuleApiClient.request_bound`) rather than the constant beside it, so one wiring test
    reads both: no other seam lets a test read what the composition hands the lifecycle without patching it. The two
    doubles a test module held moved to `tests/fakes/` (`FakeRaisingNodeMetricStore`, exempted from its contract as a
    stub, and `FakeSlowCommunityNotifier`), as `test_fake_files.py` requires. `architecture.md` §10: the sends finished
    at the shutdown, a bug in one whose turn was cut.
  - **55**: none from the spec. From the draft (`753da98d`, #751's shield alone): the dispatcher holds its shielded
    tasks in a `set[Awaitable[None]]`, not `set[asyncio.Task[None]]`, so `shield` is the only name the core gains;
    `ObservabilityOverFakes` takes the notifier at construction (the draft assigned it after, which here would not
    reach the dispatcher); `FakeHeldNotifier.wait_until_sent` returns after its timeout with nothing kept, so a test
    fails on its assertion over the notification sent, not on a `TimeoutError`; the tests assert the notification
    itself and, for the two steps, the decision row or the completed state written before the cut.
    `architecture.md` §10 says a decided notification is sent even when its turn is cut.
- **Class 1**: block 10's above; none in blocks 20 to 55.
- **Class 2 questions**: one, block 10's line bound, answered "A" (2026-11-16).

## The holistic review's findings, and their exits

1 MAJOR, 13 MINOR; every one fixed in the closing block (the lead's choices, 2026-11-16).

| Finding | Exit |
|---|---|
| MAJOR: `raise ... from None` wiped a bug's cause from its trace | fixed: the turn's exception kept out of the race's task group, re-raised after it; `test_a_bug_is_logged_with_the_exception_it_was_raised_from` |
| a login cancelled in flight left its httpx client open | fixed: the first stack's `867df1c4` brought here, `test_a_login_cancelled_in_flight_closes_its_session` |
| a bug in a shielded send whose caller was cancelled reached no turn | fixed: a done callback, added once the caller is cancelled, logs it `bug in the notification of <event>` through `Logger.exception`; `test_a_bug_in_a_shielded_dispatch_its_caller_left_is_logged_with_its_kind` |
| a send in flight at the shutdown was cut once the lifecycle returned | fixed: `CrawlerLifecycle.run` awaits `finish_shielded_dispatches` after the supervisor, within the armed deadline; `test_crawler_lifecycle.py::test_a_completion_still_sending_at_the_shutdown_is_sent_before_the_run_returns` and the dispatcher's two |
| `backoff %.1fs` | fixed: `backoff %g s`, `test_a_refused_search_warns_with_its_backoff_in_seconds`, `test_an_unreachable_client_warns_with_its_backoff_in_seconds` |
| the words the lot made false | fixed: `sqlite_sql_executor.py` ("a bug ... propagates, and fails its turn"), `_send`'s "never a bug", `download_cycle.py`'s "a cancellation (the shutdown, the time limit)" |
| the spec ids in comments | fixed: `START_SPACING`'s comment, the dispatcher's `(E-D13)`, the composition's `§11` and `§14`, `store_error.py`'s, each reason stated in place or dropped |
| `_within_time_limit`'s four-line docstring | fixed: two lines |
| `SupervisedWork.__post_init__`, `of_search`'s `ValueError` | fixed: both removed with their tests, Kad `of_search`'s `else` |
| the composition's limits untested | fixed: `test_crawler_composition_wiring.py::test_each_work_is_handed_the_time_limit_its_path_bounds`, which also holds the request bound reaching the adapter |
| TDD shown only on mutations | fixed: re-watched on stubs where the code can be stubbed, recorded below either way |
| the names | fixed: `..._raises_for_the_supervisor_to_log`, the pacing tests' "Kad word", `SearchTimeLimitOf` |
| the spec's missing `(Corrected: ...)` | fixed: D9, section 5's block 55, appendix A blocks 10 and 40 (and lot 4b4 block 40's cancelled login, brought here), appendix B's "Kad bug" and "Time limit" |
| #776's reading guide and the handoff's words | fixed: #776's guide with every block's names and "five", by `gh pr edit`; this handoff's `_send` |
- **`docs/migration-4x.md`**: untouched by the lot; no sentence of it became false (blocks 20, 40).

## The tests watched failing

Each behaviour test watched failing on its assertion, over a stub of its code, the rest of `src` as the block left it,
`__pycache__` cleared after each change; never a `TypeError`, an import or a collection error.

| Block | Test | Stub | Failure |
|---|---|---|---|
| 10 | `test_every_error_a_driven_port_declares_is_an_expected_error` (5 cases) | `ExpectedError` declared, no error re-based | `AssertionError: assert False` / `where False = issubclass(<class '...ClientError'>, ExpectedError)` |
| 10 | `test_an_exception_writes_an_error_record_carrying_the_errors_trace` | `StdlibLogger.exception` a `pass` | `assert [] == [(40, 'bug in...('channels'))]` |
| 10 | `test_an_exception_keeps_its_error_beside_its_error_line` (fake) | `FakeLogger.exception` a `pass` | `assert [] == [LoggedLine(l...('channels'))]` |
| 10 | the five names (status, download, source tracking, search, `SearchWorker.client_name`) | `__str__` returning `""`, `client_name` `ClientName("")` | `assert '' == 'status reading amuled'`; `assert ('', ('kad',)) == ('amule-1', ('kad',))`, the same for each |
| 10 | the eight supervisor-run tests | stub A: the turn catches nothing, `main`'s behaviour | `ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)` |
| 10 | `test_an_expected_error_fails_its_turn_alone_in_one_warning_line` | stub B: every exception swallowed silently, no wait after a bug | `assert [] == [LoggedLine(l..., error=None)]` |
| 10 | `test_a_bug_fails_its_turn_alone_logged_with_its_trace` | stub B | `assert [1.0, 2.0, 3....5.0, 6.0, ...] == [1.0, 61.0]` |
| 10 | `test_two_turns_of_a_work_meeting_a_bug_at_once_are_never_closer_than_60_s` | stub B | `assert [1.0, 2.0, 3....5.0, 6.0, ...] == [1.0, 61.0, 121.0, 181.0]` |
| 10 | `test_after_a_turn_that_worked_the_work_waits_its_own_wait_alone_again` | stub B | `assert [10.0, 20.0, ....0, 60.0, ...] == [10.0, 70.0, 80.0, 90.0]` |
| 10 | `test_a_bug_on_every_kad_search_leaves_the_ed2k_searches_going_on` | stub B | `{'kad': [0.0, 0.0, 30.0, 30.0, 60.0, 60.0, ...]} != {'kad': [0.0, 0.0, 90.0, 90.0]}` |
| 10 | `test_a_bug_on_one_keywords_searches_leaves_the_other_keyword_searching` | stub B | `{'keroro': [0.0, 30.0, 60.0, 90.0]} != {'keroro': [0.0, 90.0]}` |
| 10 | `test_after_a_bug_a_wait_of_its_own_longer_than_60_s_is_waited_alone` | **mutation only**: it passes on stub B, as it must, and stub A fails it on the `ExceptionGroup`; the 60 s slept, then the own wait | `assert [100.0] == [100.0, 200.0]` |
| 10 | `test_a_password_refused_at_every_reading_fails_each_turn_and_the_node_runs_on` | the real supervisor, the stamp removed (stub B spins) | `Left contains 5 more items, first extra item: LoggedLine(level='error', message='bug in status reading amuled', error=IndexError('pop from empty list'))` |
| 10 | `test_a_reading_that_raised_waits_a_full_minute_before_the_next` | no `finally` | `assert [] == [datetime.tim...a(seconds=60)]` |
| 10 | `test_after_a_turn_that_raised_the_next_waits_the_poll_interval_too` | no `finally` | `assert [] == [datetime.tim...a(seconds=30)]` |
| 10 | `test_a_store_failure_reading_the_tracked_downloads_leaves_the_turn_unlogged` | the parent's catch | `Failed: DID NOT RAISE StoreError` |
| 20 | `test_search_worker.py`'s three refused-search tests | the search still returning | `Failed: DID NOT RAISE SearchFailedError` |
| 20 | `test_search_worker.py`'s three unreachable-client tests | the same | `Failed: DID NOT RAISE ClientUnreachableError` |
| 20 | `test_backoff_saver.py::test_a_search_left_by_an_exception_after_changing_the_backoff_still_saves_it[a-search-that-raised, a-search-cancelled]` | `saving()` without its `finally` | `AssertionError: assert [] == [{BackoffKey(...annel='kad')}]` |
| 20 | `test_keyword_search.py::test_a_failed_search_fails_its_turn_as_an_expected_error_once_its_backoff_is_saved[a-refused-search, an-unreachable-client]` | the search still returning | `Right contains one more item: LoggedLine(level='warning', message="search 'keroro' amuled kad: refused", error=None)` |
| 20 | `test_a_refused_password_fails_the_search_and_backs_nothing_off` | passes at once, a guard; mutation `except (ClientUnreachableError, ClientError)` | `AssertionError: assert {BackoffKey(c...a(seconds=2))} == {}` |
| 30 | `test_amule_api_client_transport.py::test_an_answer_trickled_past_the_request_bound_is_an_unreachable_daemon` | `request_bound_seconds` stored and unused | `AssertionError: the request outlived its 0.5 s bound` / `assert set() == {<Task pendin...k_wakeup()]>>}` |
| 40 | the contract on `FakeSearchStartStore` | keeping nothing | `Failed: DID NOT RAISE StoreError`; `assert [] == [LatestSearch...]`; `assert () == (LatestSearch...,)`; `assert [] == [datetime.timedelta(0)]` |
| 40 | the contract on `SqliteSearchStartStore`, the opener | returning `()`, the migration in place; before the migration | the same; `assert [] == [{'client_nam...258400123456}]`; `Failed: DID NOT RAISE PersistenceError`; `assert {'backoff_sta...uation_state'} == {...}` |
| 40 | the adapter's starts (20 s old, an hour ahead, a client built 20 s after another, written as reserved, a refused start, unreadable, unwritable) | its read returning nothing, its write doing nothing | `assert [0.0, 60.0] == [40, 100]`; `assert [0.0, 60.0] == [60, 120]`; `assert [0.0, 20.0] == [0, 60]`; `assert set() == {LatestSearch...}`; `assert () == (LatestSearch...,)`; `assert [] == ['latest sear...s not spaced']`; `assert [] == ['search star... start early']` |
| 40 | 70 s old, another client, channel or scope, a keyword without a Kad word | pass on that stub, as they must; mutations of the key and of the remaining wait | `[the ed2k scope on kad]`, `[the kad word on ed2k]`, `assert [60.0, 120.0] == [0, 60]` |
| 40 | `test_crawler_composition_wiring.py::test_a_search_start_the_previous_run_wrote_holds_the_ed2k_search_and_kad_s_is_written` | the adapter stubbed; its write alone stubbed | `assert ['global', 'kad'] == ['kad']`; `assert [('ed2k', '')] == [('ed2k', '')...d', 'keroro')]` |
| 50 | `test_a_turn_still_running_at_its_time_limit_is_cut_as_a_bug_and_its_work_goes_on` | a supervisor that never cuts a turn | `assert [0.0] == [0.0, 90.0, 180.0]` |
| 50 | `test_a_time_limit_that_is_not_positive_is_refused[0 s, -1 s]` | no check | `Failed: DID NOT RAISE ValueError` |
| 50 | `test_work_time_limits.py`'s 7 tests | every limit the margin alone | `assert datetime.timedelta(seconds=300) == ...`; `Failed: DID NOT RAISE ValueError` (a channel aMule lacks) |
| 50 | `test_ten_ed2k_keywords_queued_on_the_client_each_search_within_its_time_limit` | an eD2k limit counting no search ahead | `At index 6 diff: 'keroro 01' != 'keroro 07'` |
| 50 | the race's `ExceptionGroup` unwrapped | **re-watched by the closing block on a stub**, the race neither unwrapping nor keeping the turn's exception out, the rest of the closing block's code | `assert [10.0] == [10.0, 20.0, 30.0]`; `error=ExceptionGroup('unhandled errors in a TaskGroup', [KeyError('channels')]) != error=KeyError('channels')`; `message='bug in hung work', error=ExceptionGroup(..., [TurnTimeoutError()]) != message='hung work: past its time limit of 30 s'` |
| 55 | `test_observability_dispatcher.py::test_a_shielded_dispatch_whose_caller_is_cancelled_mid_send_still_sends` | `dispatch_shielded` awaiting `dispatch` directly, unshielded | `AssertionError: assert [] == [(<Audience.C...tar-node-1'))]` / `Right contains one more item: (<Audience.COMMUNITY: 'community'>, CompletedDownload(...))` |
| 55 | `test_download_tracker.py::test_a_turn_cut_between_a_completion_s_write_and_its_send_still_notifies` | the same | `AssertionError: assert [] == [CompletedDow...node_id='n1')]` |
| 55 | `test_file_judge.py::test_a_turn_cut_between_a_decision_s_write_and_its_send_still_notifies` | the same | `AssertionError: assert [] == [TierRise(tie...node_id='n1')]` |
| 55 | the two step tests again | the shield in place, the file judge and the tracker back on the plain `dispatch` | `assert [] == [CompletedDow...node_id='n1')]`; `assert [] == [TierRise(tie...node_id='n1')]` |

- **Passing on the stubs, as they must**: block 10's `test_each_turn_comes_after_its_wait_the_first_included`, the
  starvation test, the stop and shutdown tests and `test_a_wait_that_raises_escapes_...` (behaviour `main` has);
  block 50's yield removed, held by the starvation tests already there, passing unchanged.
- **Block 40's UTC test** first failed on an unpack (`ValueError`), then was rewritten to assert on the list. The
  closing block re-watched it on the SQLite store reading a naive instant (`.replace(tzinfo=None)`):
  `assert [None] == [datetime.timedelta(0)]`.
- **The guards that pass at once, by design**: block 20's refused password and block 40's 70 s and other keys, shown on
  mutations above.
- **The closing block's own**, each on its assertion, before its code or over a stub of it:

| Test | Stub | Failure |
|---|---|---|
| `test_supervisor.py::test_a_bug_is_logged_with_the_exception_it_was_raised_from` | the stack's `raise ... from None` | `assert None is KeyError('channels')` / `where None = RuntimeError('a mapping bug').__cause__` |
| `test_amule_api_client.py::test_a_login_cancelled_in_flight_closes_its_session` | `except Exception` | `assert transport.closed` / `assert False` |
| `test_observability_dispatcher.py::test_a_bug_in_a_shielded_dispatch_its_caller_left_is_logged_with_its_kind` | no done callback | `level: 'info' != 'error'` (the dispatch's own line last, no bug line) |
| `test_crawler_lifecycle.py::test_a_completion_still_sending_at_the_shutdown_is_sent_before_the_run_returns` | no `finish_shielded_dispatches` call | `At index 0 diff: <Audience.OPERATIONS: 'operations'> != <Audience.COMMUNITY: 'community'>` (the completion never sent) |
| the dispatcher's two `test_finishing_the_shielded_dispatches_...` | `finish_shielded_dispatches` waiting for nothing | `assert not True`; `assert [] == [LoggedLine(l...etrics bug'))]` |
| `test_search_worker.py`'s two `..._warns_with_its_backoff_in_seconds` | `%.1fs` | `'... failed (refused): backoff 2.0s' != '... failed (refused): backoff 2 s'`, the same for the unreachable client |
| `test_amule_api_client.py::test_the_client_declares_the_bound_it_sets_on_each_request` | `request_bound` returning `timedelta(0)` | `assert datetime.timedelta(0) == datetime.timedelta(seconds=60)` |
| `test_crawler_composition_wiring.py::test_each_work_is_handed_the_time_limit_its_path_bounds` | no debug line | `assert [] == ['status read... 2400 s", ...]`; then on mutations: the limits given the 10 s phase timeout (`'status reading amuled: time limit 470 s' != '... 1070 s'`), the raw keywords (`"search 'keroro mission' amuled ed2k: time limit 3240 s" != '... 2400 s'`), `of_tracking()` for the status reading (`'... 1030 s' != '... 1070 s'`), the adapter given the 10 s timeout as its bound (`'... 470 s' != '... 1070 s'`) |
- **Block 40's `test_a_restart_re_evaluates_the_catalogue_only_once_a_policy_file_changed`** failed on `assert False`
  (its second run waited for the first's start), fixed by deleting the starts' rows between its runs.

## Section 4's rows, where each is held

| Row | Test |
|---|---|
| A bug on every Kad search | `test_keyword_search.py::test_a_bug_on_every_kad_search_leaves_the_ed2k_searches_going_on` |
| A bug on one keyword's searches | `test_keyword_search.py::test_a_bug_on_one_keywords_searches_leaves_the_other_keyword_searching` (its backoff untouched, D11) |
| A work raising a bug at once, turn after turn | `test_supervisor.py::test_two_turns_of_a_work_meeting_a_bug_at_once_are_never_closer_than_60_s` (its own wait 1 s) |
| A turn that never returns | `test_supervisor.py::test_a_turn_still_running_at_its_time_limit_is_cut_as_a_bug_and_its_work_goes_on` |
| Ten eD2k keywords queued on the client's lock | `test_keyword_search.py::test_ten_ed2k_keywords_queued_on_the_client_each_search_within_its_time_limit` |
| A password refused while the node runs | `test_status_watcher.py::test_a_password_refused_at_every_reading_fails_each_turn_and_the_node_runs_on`; the search, `test_search_worker.py::test_a_refused_password_fails_the_search_and_backs_nothing_off` |
| aMule sending its answer byte by byte | `test_amule_api_client_transport.py::test_an_answer_trickled_past_the_request_bound_is_an_unreachable_daemon` |
| A node restarted within a minute of a search start | `test_amule_api_client_search_pacing.py::test_a_start_stored_20_s_ago_holds_the_first_start_of_a_client_built_anew_40_s`, `::test_a_start_stored_70_s_ago_holds_no_start_of_a_client_built_anew` (eD2k and a Kad word shared by two keywords); through the composition, `test_crawler_composition_wiring.py::test_a_search_start_the_previous_run_wrote_holds_the_ed2k_search_and_kad_s_is_written` |
| A turn cut between a decision's write and its notification | `test_file_judge.py::test_a_turn_cut_between_a_decision_s_write_and_its_send_still_notifies`; a completion's, `test_download_tracker.py::test_a_turn_cut_between_a_completion_s_write_and_its_send_still_notifies`; the dispatcher alone, `test_observability_dispatcher.py::test_a_shielded_dispatch_whose_caller_is_cancelled_mid_send_still_sends` |

The two step tests cancel the task running the turn, which is what the supervisor's race does when the expiry raises;
no test runs that cut through the supervisor itself.

## What must not change

| Check | Result |
|---|---|
| The matching decisions on the real catalog | **not run**: the umbrella's comparison reads the operator's `catalog.db`, outside the repository. The lot touches no matching code: `git diff --name-only origin/main...HEAD -- packages/crawler/src/p2pwatch/domain/matching packages/crawler/src/p2pwatch/adapters/driven/config` lists nothing (2026-11-16), and the gate's golden corpus passes |
| `deploy/matcher.yml` and its keys | `git diff --stat origin/main...HEAD -- deploy/matcher.yml deploy/targets.yml` empty; `validate-config` on `deploy/`, `AMULE_API_PASSWORD` set to a placeholder: `Config valid` (2026-11-16) |
| A healthy node's notifications, a channel's search cadence | at the release candidate |

## The lot's counts

- Fix-backs: 0. Cascaded rebases: 0.
- Runs re-triggered: 0 so far.
- Bodies the operator called unreadable: 0.
- Past a bound, the operator's acceptances: block 10's lines, "A" (2026-11-16), its files and block 40's on the spec's
  rows.

## For lot 7 (the operator pages)

- The supervisor's lines: `bug in <work>` with its trace, `<work>: <error>`, `<work>: past its time limit of
  <seconds> s`; each work's name as above.
- A failed search is logged twice, by the search worker and by the supervisor; the worker's line writes
  `backoff <seconds> s`.
- A notification in flight at the shutdown is sent before the node stops; a bug in a notification whose turn was cut
  is logged `bug in the notification of <event>` with its trace.
- At debug level, each work's time limit at the start: `<work>: time limit <seconds> s`.
- Source tracking's store failure reading its tracked downloads is logged by the supervisor, no longer by source
  tracking.
- A password refused while the node runs no longer stops it.
- A request to aMule is cut at 60 s in all, an unreachable client.
- The new `local.db` table `latest_search_starts`; a node restarted within a minute of a search waits before that
  channel's next search; the starts store's two error lines, `latest search starts not read (<error>): the first
  starts not spaced` and `search start not written (<error>): a client built anew may start early`.

## Pitfalls learned

- **A stub that swallows bugs without the 60 s spins any test whose work waits nothing and raises at once**: run such
  stubs under `timeout` (block 10; the password test spun through `FakeStatusClient`'s empty list, an `IndexError`).
- **`BackoffSaver.saving()` saves when a turn is cancelled too**, a synchronous write in its `finally` (block 20).
- **`VirtualLoop` refuses any real I/O**: the trickling socket runs on the real loop with sub-second bounds; a bound
  raced against `FakeTime`'s sleep would win every race (block 30).
- **`FakeAmuleApi` keeps only its `FakeTime`'s monotonic clock**: tests outside the pacing module give the client a
  wall clock of another `FakeTime`, harmless where no test checks pacing (block 40).
- **A docstring inside the compose smoke's `f"""` script ends the string**: a comment instead (block 40).
- **`no-protocol-base` exempts a callback `Protocol` only when `__call__` is its sole member**: a docstring in its
  body breaks the exemption; a one-line comment above the class instead (block 50).
- **Under `FakeTime`'s instant sleeps every time limit expires at once**: the lifecycle's tests moved to
  `FakeBlockingMonotonicClock` (block 50).
- **A shielded send outlives its turn** (block 55): the dispatcher holds its task, the loop keeping only a weak
  reference to a task. Once the lifecycle returns, `asyncio.run` cancels every task left, so the lifecycle finishes
  them first (closing block).
- **A bug in a shielded dispatch whose caller was already cancelled reaches no turn**: nobody awaits it, so on its own
  it surfaces only as asyncio's "Task exception was never retrieved" (probed on Python 3.13.6, 2026-11-16); the done
  callback logs it instead (closing block).
- **`raise error from None` rewrites the error itself**: its `__cause__` set to `None`, its `__context__` hidden, so a
  re-raise that only unwraps loses the cause from the trace. An exception raised in a `TaskGroup`'s body is wrapped in
  its `ExceptionGroup` too; caught inside the body, it is never wrapped (closing block).
- **`test_fake_files.py` refuses a port's implementation in a test module**, a local subclass of a fake included: a
  double lives in `tests/fakes/`, and a stub among them is exempted in `test_contract_subclasses.py` (closing block).
- **A done callback's argument cannot be annotated in the core**: `asyncio.Task` and `asyncio.Future` are not among the
  core's asyncio names, so the callback is a lambda over the task's own methods (closing block).
- **`ObservabilityOverFakes` takes its notifier at construction** (block 55): assigning `.notifier` afterwards
  replaces the attribute, not the dispatcher's notifier.

## Not validated

- Nothing ran against a real node: no turn cut, no limit measured against a real aMule's timings, no node restarted
  within a minute of a search, no amuled stalling mid-answer, no write cost of the starts on the node's disk.
- **The `orchestration_integration` suite passed** at the closing block's tip (`2f5bbf0d`, 2026-11-16):
  `test_real_loop_runs_one_search_and_stops`, 1 passed, against `p2pwatch-amule:dev` built from the tree, `-p
  14711:4711`, `P2PWATCH_TEST_API_HOST=127.0.0.1 P2PWATCH_TEST_API_PORT=14711`. `api_integration` and
  `download_integration` did not run at the closing block, whose adapter changes (a property, the login's `except`)
  their unit tests hold.
- **Integration suites before it**, against `p2pwatch-amule:dev` built from the tree, `-p 14711:4711`,
  `P2PWATCH_TEST_API_HOST=127.0.0.1 P2PWATCH_TEST_API_PORT=14711`: block 30, `api_integration`,
  `download_integration` and `orchestration_integration`, 6 passed (2026-11-16, on `672600f1` with the block's code);
  block 40, `api_integration` and `download_integration` 5 passed, `orchestration_integration` 1 passed; block 50,
  `orchestration_integration` 1 passed. `compose_integration` not run (block 40): the test that runs its script
  reads a completion, which fails under this machine's Docker Desktop; the script was parsed with `ast.parse`.
  Blocks 10, 20 and 55 ran no Docker suite: no adapter changed but `StdlibLogger` (block 10).
- The spin a refused password would cause without the restored stamps is reasoned from the code, not observed
  (block 10).
- The matching comparison on the real catalog (What must not change).
- No turn was cut through the supervisor itself between a decision's write and its send: the step tests cancel the
  task running the turn, as the race does.

## `BACKLOG.md`

Reconciled: the lot adds nothing, and the sub-entry 4b stays open until lot 4b5.

## Next step

The operator reads and merges the stack, rebased onto `main` if it moved. No release: v5 ships after lots 4c to 7 and
their release candidates.

Then lot 4b4, the restarts of the aMule client (the spec's section 5 and appendix A, "Lot 4b4"): the bugs rule
recorded by the supervisor on one component per work and on each channel (block 10), "searches failed" and "connected
to no network" (block 20), the works over the client built by one function of the composition (block 30), and
`Restartable`, `RestartPolicy`, the client rebuilt, three times in vain at most (block 40, with #751's restart fixes
and #752's holder; its cancelled login is already closed, by this lot's closing block). Its own stack from `main`, once lot 4b3 has merged. D16's "or its object rebuilt" rests on this
lot's shield: a rebuild stops the works, and a send in flight finishes.

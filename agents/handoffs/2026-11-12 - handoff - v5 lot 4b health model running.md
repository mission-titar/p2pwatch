# Handoff: v5 lot 4b, the health model running (tier Spec)

Drafted by block 74's teammate from the block reports (#718 to #746, the collapsed "Block report" of each pull request
body) and the lead's facts, corrected by the closing block (90) with the holistic review's exits. Spec:
`agents/specs/2026-11-09-v5-fault-isolation.md`, lot 4b of its three (D21), under
`agents/specs/2026-11-04-v5-release-readiness.md` (the umbrella), whose D12 and D13 the whole lot 4 implements.

## Current state

- **The node id is resolved by the composition before the graph** (block 10): right after the node id store opens,
  before the webui; every step that writes it receives it at construction. Today (`git grep -l -w 'node_id: NodeId'
  -- src/p2pwatch/application/steps`, 2026-11-12) these are the cataloguer, the file judge, the download tracker, the
  source watcher and the health event translator; the status loop's went with its timers (block 27), the download
  decider's with `DiskSpaceLow`'s (block 60). `CatalogReevaluator`, `SearchWorker`, `SearchTaskRunner`,
  `DownloadCycle` and `DownloadLoop` only passed it on and lost it. The stores keep it where it is the value written or
  a query key. The glossary's `step` is "a stage of the program the composition builds, behind no driving port".
- **Every failure a driven port declares derives from `DeclaredFailure`** (D3 whole, block 40), `ClientAuthError`
  with `ClientError`, so a password refused while the node runs is a declared outcome each turn, the node running.
  The reasons never raised are `DeclaredFailure`s too: `ClientNotAnswering`, `ChannelNotConnected`,
  `ChannelNotConnectable`, `NoChannelConnected`, `FreeSpaceBelowFloor` (its `free_bytes`, `min_free_bytes`),
  `NotificationTimedOut`; `NotificationRefused` is the notifier's raised failure.
- **The health library** (`domain/health/`, pure, blocks 20, 27, 50, 52, 60): `Outcome` (a success, a declared reason
  or a `Bug` carrying a description), `OutcomeSource`, `Health` (unknown, healthy, degraded, failing),
  `HealthCondition` counting one reason among a component's last outcomes of one source, with a failing and a degraded
  `Band` (`AtLeast` to enter, a stricter `Below` to leave; the defaults failing at 3 of 3 leaving below 2 of 10,
  degraded at 2 of 10 leaving below 1 of 20, written once as the fields' defaults), `ConditionWindow`, `Component`
  (its `ComponentLabels`, `client_name` optional, `channel`; `reads`, `health_of`, `empty_windows(of=)`, `record`)
  and `HealthTransition` (component, condition, `previous`, `current`, the `outcome` that changed it). While failing
  holds, degraded is not held; on leaving failing, degraded enters only by its own entry. A condition is unknown until
  its window holds its smallest entry's outcomes; a success counts for every condition of its source.
- **`HealthRecorder`** (`application/steps/`, block 20): every outcome's one path, `record(outcome, on=, by=)`, the
  turns' and the sends' source named `UNITS_OF_WORK` ("a unit of work's outcome: a supervised turn or a notification's
  send", block 90, `TURNS` before); each
  transition logged in one line (`<component>, <condition>: <previous> to <current>`, a warning into degraded or
  failing, an info otherwise), then handed to its subscribers in order: `HealthEventTranslator`, then `RestartPolicy`.
- **The conditions per component**, as the composition builds them:

  | Component (its name) | Conditions | Source of each |
  |---|---|---|
  | `client amuled` | unreachable (failing at 3 of 3) | `STATUS_API_ANSWER` |
  | `channel amuled ed2k`, `... kad` | not connected (failing at 6 of 6), not connectable (degraded at 6 of 6), searches failed (`SearchFailedError`, default bands; a search turn records a success or a refusal only, block 90), bugs | `STATUS_CONNECTED_FIELD`, `STATUS_CONNECTABLE_FIELD`, `SEARCHES`, `UNITS_OF_WORK` |
  | `search '<keyword>' amuled <channel>` | bugs | `UNITS_OF_WORK` |
  | `status sensor amuled`, `source tracking amuled` | bugs | `UNITS_OF_WORK` |
  | `download tracking amuled` | bugs, connected to no network (the channels' band, 6 of 6), disk space low (degraded at 1 of 1, leaving at the first good reading) | `UNITS_OF_WORK`, `STATUS_CONNECTED_CHANNELS`, `FREE_SPACE_READING` |
  | `webui` | bugs | `UNITS_OF_WORK` |
  | `notifier <scheme> <audience>` per notification URL (`... 2` for a second alike) | bugs, sends failed (`NotificationFailed`, a refusal or a timeout, default bands, block 90) | `UNITS_OF_WORK`, `SENDS` |

  Each work names itself in the log as the component it feeds (block 90), each owner `owner of client amuled`,
  `owner of the webui`, `owner of the notifier`.

  An unknown reading (the client unreachable) records nothing on the channels' and download tracking's conditions.
  The client's component carries no bugs condition: no work feeds it.
- **`HealthEventTranslator`** turns the readings' transitions into today's events: entering a band sends the alert
  ("for 2 min", "for 5 min", derived by `lasting_at_entry`), only a return to healthy after it the end, unknown to
  healthy nothing; `DiskSpaceLow` from the disk's entry, with its figures; no event for any other condition, nor for
  a component without a client (the webui, the notifier's services), so a failing notifier never notifies about
  itself. `_AlertTimer`, `CHANNEL_ALERT_AFTER` and `EdgeState` are gone.
- **The works and the supervisor** (blocks 30 to 47): `Work`, an ABC (`wait_for_next_turn()`, `run_once()`,
  `__str__`); the works are `StatusSensor` (renamed from `StatusLoop`, its wait from its latest turn's end, set in a
  `finally`), `DownloadCycle` (download tracking, at the poll or the wake, the first turn at once), `SourceWatcher`
  (source tracking, `sources_interval` start to start), one `KeywordSearch` per client, channel and keyword (the
  composition enumerating them with `dedupe_keywords` and the worker's channels), and `WebuiLiveness` (one status
  period before each turn). `Supervisor` (renamed from `LoopSupervisor`) runs each `SupervisedWork`'s turns: the wait
  outside the limit, the turn raced in a `TaskGroup` against `MonotonicClock.sleep` of its time limit, the outcome
  recorded by `UNITS_OF_WORK` on the components the work `feeds` (required, refused empty or reading none). A declared
  failure is a warning `<work>: <reason>`; anything else a `Bug`, `bug in <work>` with its trace, the next turn
  waiting the later of `FLOOR_AFTER_A_BUG` (60 s) and its own wait; a turn past its limit is a `TurnPastItsLimit`,
  a `Bug`, logged without a trace. The shutdown arms its bound, then cancels every work, a restart in flight
  included. `BackoffSaver` saves the backoff after each search turn, in a `finally`, its snapshot at the first turn.
  `DownloadLoop`, `SearchTaskRunner` and `Work.run()` are gone.
- **The time limits** (block 47): `AmuleTurnTimeLimits` derives each aMule work's limit as the sum of the bounds on
  its turn's path plus `TIME_LIMIT_ALLOWANCE` (5 min): the status reading `2c + (1 + 2 x channels)N`, an eD2k search
  `(K-1)·max(S, B+2c) + S + B + 3c`, a Kad search `K_w·S + 2B + 4c`, download and source tracking `2c + N` each; the
  webui's liveness the allowance alone. The adapter publishes `START_SPACING`, `ED2K`, `KAD`, `kad_word_of`.
- **amuleapi's request bound** (block 45): each request bounded at 60 s in all (`_AMULE_API_REQUEST_BOUND_SECONDS` in
  the composition, passed as `request_bound_seconds`), its expiry a `ClientUnreachableError`.
- **The latest search starts persisted** (block 46): `latest_search_starts` in `local.db`, keyed by the client's
  name, the channel and a scope (`''` for eD2k's channel-wide spacing, the Kad word on Kad), each start's own instant
  written as reserved; `SqliteSearchStartStore`, `FakeSearchStartStore` (which can refuse its writes) and their
  contract; a client built anew, at a restart of its owner or at the process's start, spaces its first starts from
  them, `remaining_wait` clamping a persisted wait. A `StoreError` is logged at error level, the read letting the
  client start as today, the write letting the search go on.
- **The restarts** (blocks 52a, 52, 65, 68, 72, 90): `StateOwner` (a port with `restart()` and `__str__`, its
  `StateOwnerContract`, `FakeStateOwner` in `tests/fakes/composition/`); `RestartPolicy`, the recorder's subscriber,
  requests the restart of the owner of a component whose bugs condition enters failing: a `RestartRequest` (its owner,
  its components, `rebuilt()` emptying their bugs windows, `rebuild_raised()` counting it useless) through an
  `asyncio.Queue` the supervisor reads, the restart in a task of the supervisor, the works feeding the owner's
  components cancelled and awaited before each attempt (block 90); a restart is useless when a bugs condition of the
  owner's components fails again before all are healthy, or when the rebuild raised (a `Bug` on each component, tried
  again after the floor). After three rebuilds that raised, nothing of the owner's work runs until the container
  restarts; after three useless restarts whose rebuilds succeeded, the works run on, only the buggy turns failing, and
  the count resets once every bugs condition of its components is healthy again (answer 21). Every component the
  policy reads is owned, the no-owner branch deleted (block 90). The owners: `AmuleClientOwner` (rebuilding every
  object holding the client through `AmuleWorks.over`, the resource stack closing the current instance),
  `WebuiThreadOwner` (through `WebuiWorks.over`), and `NotifierOwner`, through which the dispatcher reaches the notifier
  at each send (`current_notifier`). `component_owners` maps each component to its owner from the works' factories
  and the notifier's services; `PartsBuiltLater` holds the recorder and the supervisor for the parts built before them
  (the dispatcher, the download decider, the owners, the factories), a read before either is set a
  `PartNotBuiltYetError` (block 90).
- **The notifications** (blocks 70, 72, 74): the `Notifier` port lists its `NotificationService`s (a scheme, an
  audience, an ordinal) and sends to one; `AppriseNotifier` holds one apprise object per node and service, its URL
  alone. The dispatcher sends a notification to each service of its audience concurrently, each under
  `notification_timeout_seconds`, and records each send's outcome on that service's component: by `TURNS`, and by
  `SENDS` unless a bug. A refusal (any apprise answer but a success) is `NotificationRefused`, a send past the timeout
  `NotificationTimedOut`, both `NotificationFailed`, declared; anything else a `Bug`. Nothing a notification does breaks
  the crawl. A decision's sends after its write, and a completion's, run through `dispatch_shielded`, so a restart or a
  time limit cancelling the turn loses none (block 90, `asyncio.shield` in the core's names). `NotifierContract`:
  `AppriseNotifier` and `FakeNotifier` run it.
- **Not yet, lot 4c's**: the graph and a component's propagated health, the root causes and one alert per root cause,
  the open alerts across a restart, `/health/*`, the health metrics, the loop watchdog, the refused password as a
  condition (its block 73), the databases as components, the reevaluation's condition. The connectivity and disk
  alerts are still today's events, produced by the conditions.

## What was built, block by block

Stack order, bottom to top; 52a sits below 52.

| # | PR | Block | Lines, files |
|---|---|---|---|
| 10 | #718 | the node id resolved by the composition, every step receiving it at construction | 406, 30 (411, 31 with the lead's first commit) |
| 20 | #719 | the health library, the recorder and its log line, the translator; the client's unreachable condition | 738, 22 |
| 25 | #721 | each channel's not connected condition replaces its connected timer | 386, 9 |
| 27 | #722 | each channel's not connectable condition, degraded, replaces the last timer | 233, 13 |
| 30 | #723 | `Work`, the status reading the first work, `Supervisor` one class | 276, 18 |
| 33 | #724 | the download cycle's round named `run_once` | 91, 7 |
| 34 | #725 | download tracking as a work, `DownloadLoop` removed | 449, 10 |
| 35 | #726 | source tracking as a work of its own | 446, 11 |
| 36 | #727 | one search work per client, channel and keyword, `SearchTaskRunner` removed | 469, 12 |
| 38 | #728 | the turn loop in the supervisor, `Work.run` removed | 249, 10 |
| 40 | #729 | each turn's outcome, a bug failing its turn alone, the floor after a bug | 454, 29 |
| 41 | #730 | a failed search raised after its backoff and events, the backoff saved in a `finally` | 63, 5 |
| 45 | #733 | each amuleapi request bounded at 60 s in all | 83, 10 |
| 46 | #734 | each client's latest search starts in `local.db`, a client built anew spacing its first starts | 841, 25 |
| 47 | #735 | each work's time limit, a turn past it cut as a bug | 454, 12 |
| 50 | #736 | the bugs condition on every work's component, each turn's outcome recorded on them | 424, 19 |
| 51 | #737 | a channel's searches failed, download tracking's client connected to no network | 280, 14 |
| 52a | #739 | the works over the client built by one factory, the download steps holding no client built once | 315, 1 |
| 52 | #738 | `StateOwner`, `RestartPolicy`, the aMule client's owner, three useless restarts at most | 1198, 21 |
| 60 | #741 | disk space low as download tracking's condition | 314, 19 |
| 65 | #742 | the webui's liveness, a fallen thread a bug logged without an owner | 222, 14 |
| 68 | #743 | the webui thread's owner | 297, 6 |
| 70 | #744 | each notification's outcome on the notifier's component | 364, 16 |
| 72 | #745 | the notifier's owner, the dispatcher reaching the rebuilt notifier at each send | 242, 15 |
| 74 | #746 | the notifier's services, one component each, their sends refused | 497, 19 |
| 90 | | closing block: the holistic review's findings fixed, the spec corrected, the backlog reconciled, this handoff | 1486, 61 in 18 commits, in 8 steps each under both bounds, for the lead to cut |

Twenty-six blocks with the closing one: the spec's 22 rows (the re-cut's, accepted past the workflow's 19 by the
operator on 2026-11-11, "Je préfère un seul lot"), block 46 added on 2026-11-12, and four splits made in Act.

- **Past a bound, accepted**: block 10 past the file bound and block 20 past both (the spec's rows); block 40 at 29
  files ("recos ok", 2026-11-11, the search worker's raising apart as 41); block 46 past both ("approuvé",
  2026-11-12); block 52 past the line bound (the spec's row; at 21 files it passes the file bound too, which the row
  does not name: the closing block checks the acceptance).
- **The splits made in Act**: 25 into 25 and 27, by field (548 lines, 14 files whole); 33 into 33 and 34, the
  mechanical rename apart (538 lines, 14 files whole), so the spec's 34, source tracking, is 35 on the stack; 40 into
  40 and 41, the spec's own lever; 52a out of 52, the composition's reorganisation, behaviour unchanged (1510 lines
  whole, the operator's "reco ok" of 2026-11-12). Block 36 measured 814 lines in one commit, then 469 in two green
  commits once git saw the runner's tests renamed: no split.
- **Block 46 added on 2026-11-12**: block 45's class 2 question (below) moved the first starts' spacing out of 45 into
  a block of its own, persisted in `local.db`; the spec corrected by the lead, reviewed, then approved by the
  operator. Block 45's first patch, built on the in-memory rule, was set aside, not applied:
  `/tmp/claude-1000/-home-geoffrey-Repositories-emule-indexer/7e2d792a-38da-4b57-8719-89b9e772e9bd/scratchpad/block45-first-starts.patch`.
- **Departures, per block** (the spec's `(Corrected: ...)` marks are the closing block's):
  - Block 10: only the steps that write the id receive it at construction (`CatalogReevaluator`, `SearchWorker`,
    `SearchTaskRunner`, `DownloadCycle` and `DownloadLoop` lose it); the glossary's `step` line and the architecture
    page reworded; `test_a_task_records_its_observations_under_the_node_id_the_tasks_run_with` pruned.
  - Block 20: `ClientNotAnswering`, `STATUS_API_ANSWER` and `CLIENT_UNREACHABLE` in `domain/status_reading.py` beside
    `STATUS_PERIOD`, `lasting_at_entry` there; `ConditionWindow`, an immutable value, carries the judgement; the
    bounds keyword-only (`AtLeast(count=3, of_last=3)`, `dataclass-kw-only`); `AtLeast`, `Below` and `Band` refuse
    an incoherent count or exit (`ValueError`); `previous` and `current` for from and to; `HealthSubscriber`, a
    callback `Protocol` (TID251 bans `Callable`); the client component named `client amuled`; nine glossary lines;
    a "Santé" row in the architecture page.
  - Block 25: split by field; the connectable field kept its timer in `StatusLoop` for that block alone; an
    unreachable reading samples every channel as unknown, at boot too (two debug lines at a boot with the API down);
    `client_component` and `channel_component` in `domain/status_reading.py`; `ComponentLabels.channel` defaults to
    `None`, the translator sending nothing for a channel condition on a component without a channel.
  - Block 27: the recorder logs a transition into degraded as a warning; `HealthCondition.band()`, `failing` and
    `degraded` required (block 50 made them defaulted, `bands()`); glossary `health`, `health condition`,
    `declared failure`.
  - Block 30: `StatusLoop` renamed `StatusSensor` (the spec's block 52 row still names `StatusLoop`); its wait from its
    last turn's end, in a `finally`; `abc` added to `ast-grep/rules/application-imports.yml`; `CrawlerLifecycle`'s
    `loop_supervisor` became `supervisor`; the audit instruments under `agents/reference/` still import `StatusLoop`
    and `LoopSupervisor`, dated records left untouched.
  - Block 33: the rename by Serena's `rename_symbol` from `DownloadCycle/run`, the module docstring corrected by hand.
  - Block 34: `DownloadCycle` keeps its name; the turn's flag set first in `run_once()`, so a raised turn still waits
    a poll; the run state no longer read, the loop's two shutdown tests and `FakeShutdownDuringCycleDecisionReader`
    gone; `build_cycle` gains `poll_interval_seconds`, `waker`, `wait_clock`; the prose "download loop" left in files
    the block does not touch (the SQLite tracked download store's docstring, `FreeSpaceMeter`, `DownloadCandidate`,
    `events.py`, the fakes' messages, a migration's SQL comment) and the operator's line `download enabled: download
    loop armed`.
  - Block 35: `SourceWatcher` keeps its name; the start stamped before the list read, so reads are `sources_interval`
    apart start to start (before: the interval plus up to a round) and a failed list read waits a full interval
    (before: tried again one poll later); `time_between_source_reads` kept, its docstring corrected; its two log lines
    keep their text under the `source_watcher` logger, the first also covering the watcher's own list read; the
    wiring test waits for a second sources read (`sources_interval_seconds: 0.05`); `tests/support/.../source_watcher.py`
    added; `docs/settings.md` reworded to start to start.
  - Block 36: the work named `KeywordSearch`; the composition enumerates through `worker.channels`; the snapshot taken
    by the context manager's entry at the first turn; the runner's tests became the work's, the starvation test and
    `FakeNeverSuspendingSearchClient` removed, the keyword deduplication test with them; the search works created
    directly in the supervisor's task group (no nested group around a search's exception).
  - Block 38: `supervise(works, arm_shutdown_bound=...)` kept rather than the sketch's `add(work, feeds=,
    time_limit=)`; `test_work.py` deleted, its tests moved to the supervisor's; the test "a loop that ends neither
    stops the others nor arms the bound" removed.
  - Block 40: split (41 the search worker's raising); `Bug` a frozen dataclass beside `Outcome`; the floor raced
    against the work's wait in a `TaskGroup` (no `gather` in the core); the logger's `exception` takes the error
    explicitly; `supervise(works)` unchanged; `SearchWorker.client_name`; `FakeTimedSearchClient`'s
    `broken_keywords`, `broken_channels`; `LoggedLine.error`; a `docs/migration-4x.md` hunk dropped on the lead's
    request (lot 7's file).
  - Block 41: the spec's lever, the file bound; architecture page section 5.
  - Block 45: the first starts' spacing out to block 46; the 60 s in the composition, passed in (the 2026-10-23
    spec's D8), the integration tests passing 180 s.
  - Block 46: the composition's `tach.toml` entry unchanged (`exact = true`), the adapter's and `persistence_sqlite`'s
    gaining the pair; the client's two maps made one, keyed as the rows; a wiring test end to end and a SQLite test
    for an unreadable stored instant added; the compose smoke's script builds its client over a no-op store written
    in the script.
  - Block 47: the race in a `TaskGroup`, the turn in its waiting task, the yield after a turn removed; the two
    formulas corrected (class 1); the acceptance test over `FakeAmuleApi`'s `MockTransport` on the virtual-time loop,
    its ten keywords sharing the Kad word `keroro`; the status reading's notification count `1 + 2 · channels`; the
    webui's limit block 65's.
  - Block 50: `TURNS` in `domain/health/outcome.py`, `BUGS` in `health_condition.py`, the default bands as the
    fields' defaults (`degraded=None` to opt out); `bands()`; the translator alerting on entering degraded or failing;
    `SupervisedWork.feeds` required and checked; `domain/work_components.py`; the channel's component gains `BUGS`;
    the acceptance tests of the Kad bug and one keyword's bug run 130 s.
  - Block 51: `SEARCHES` and `SEARCHES_FAILED` in `domain/search/searches_failed.py`, `NoChannelConnected`,
    `STATUS_CONNECTED_CHANNELS`, `CONNECTED_TO_NO_NETWORK` in `domain/status_reading.py`; a bug records nothing on
    "searches failed"; "connected to no network" takes the channels' band (6 of 6), the lead's answer on the pull
    request moving the first commit's 3 of 3; `StatusSensor.download_tracking_component`, `None` without
    `download:`.
  - Block 52a: the preparation half of 52 (the operator's split); `_DownloadSteps.components()` left to 52.
  - Block 52: the cycle (policy, owner, recorder) broken by `build_works` and `add_work` lambdas, the loop over the
    works in `AmuleClientOwner`, tested; requests through an `asyncio.Queue` (`requested()`, `rebuilt()`,
    `rebuild_raised()`), `asyncio.Queue` and `asyncio.Task` added to `core-import-names.yml`, the phases a `Literal`;
    the bugs windows emptied once the rebuild succeeded; a reset after giving up too, when the works still run;
    `StateOwner.__str__`; `Component.health_of`, `empty_windows`; the policy refusing a component without a bugs
    condition; a rebuild's bug recorded by `TURNS`.
  - Block 60: `HealthTransition.outcome`; `FreeSpaceBelowFloor`, `FREE_SPACE_READING`, `DISK_SPACE_LOW` in
    `domain/download/disk_space.py`; download and source tracking's components built before the policy whatever the
    mode, given to the policy and the sensor only on a downloading node; `_DownloadSteps.components()` removed;
    `DownloadDecider` loses `node_id`.
  - Block 65: `ComponentLabels.client_name` optional; the liveness waits one period before every turn; `WebuiFallen`,
    `WebuiThreadAlive`, `UvicornServerThread.is_alive()`; the webui's limit `TIME_LIMIT_ALLOWANCE` used directly; the
    no-owner line a warning; a policy test split in two.
  - Block 68: `WebuiThreadOwner` (`webui thread` in the log), `ThreadBuilder`, `ThreadWorks`, `WorkAdder` reused; a
    rebuild whose bind fails or times out does not raise.
  - Block 70: the dispatcher records by `TURNS`, which now names a unit of work's outcome, a turn's or a
    notification's; an `OutcomeRecorder` callback `Protocol` and the component, the recorder needing the dispatcher
    first; `notifier_outcomes.py`; no `NotifierContract`.
  - Block 72: `NotifierOwner` (`notifier` in the log), `NotifierBuilder`, `CurrentNotifier`; the indirection a callback,
    an owner implementing `Notifier` having been refused by `test_each_double_sits_in_the_ring_of_what_it_replaces`;
    `StateOwnerContract.state_relied_on`, async, checked after each restart; nothing for the resource stack.
  - Block 90: the review's exits below; the index of Serena stale at its start (references at shifted lines), so the
    three renames (`TURNS`, `SENDS_REFUSED`, `_last_turn_ended_at`) went by `git grep -w` and `sed`, each a constant or
    a private attribute; `DownloadCycle` and `SourceWatcher` gain `client_name` for their log name; the download
    decider records through an `OutcomeRecorder` callback, so the download steps are built before the recorder;
    `download_steps` and `DownloadSteps` public, the steps' `targets` in place of the loaded config, their waker typed
    by its port (`tach.toml`'s composition entry gains `status_reading_writer` and `waker`); `FakeStateOwner` gains
    `raising_after_adding`, `FakeNotifier` `refusing`, `FakeHeldNotifier` added; four notifier doubles exempted from
    `NotifierContract`, each with its reason; the factories' commit and their tests' split for the line bound, the
    tests written and watched failing first.
  - Block 74: `NotificationService`, `notifier_components`, `SENDS_REFUSED` ("sends refused"), `SENDS`, in
    `notifier_outcomes.py` for the file bound; the ordinal for a second service alike (reordering two alike URLs swaps
    their names); the scheme `unknown` for a URL without `://`; "sends refused" counting `NotificationRefused` alone, a
    timeout counted by no condition; the services of an audience sent to concurrently (a `TaskGroup`), so a
    notification stays within one `N`; `NOMATCH` a refusal; still no `NotifierContract`; `NotifierOwner`'s docstring
    and the glossary's `state owner` line still say "apprise groups".

## The tests watched failing

One line per new behaviour; the block reports hold every case.

| Block | Test | Failure before the code |
|---|---|---|
| 10 | `test_a_new_node_records_its_id_before_amuled_refuses_its_password` (on `main`'s source) | `assert None is not None` |
| 20 | `tests/domain/health/`, section 4's pattern `000111000111` | `ModuleNotFoundError: No module named 'p2pwatch.domain.declared_failure'` |
| 20 | `test_status_loop.py`, the end at the ninth answer | 18 times `TypeError: StatusLoop.__init__() got an unexpected keyword argument 'health_recorder'` |
| 25 | the translator's channel cases; an unreachable reading between two failed runs | `assert [[], [], [], []] == [[RelayedLogLine(message='fake kad: off its network for 5 min', ...)], ...]` |
| 27 | the degraded band; the recorder's warning | `AttributeError: type object 'Health' has no attribute 'DEGRADED'`; `... 'channel amuled kad, not connectable: unknown to degraded'` |
| 30 | `test_work.py`, the yield | `assert ['wait', 'tur...wait', 'turn'] == ['wait', 'turn']` |
| 34 | the cycle's wait tests (mutations) | `assert [] == [datetime.tim...a(seconds=30)]`; `TimeoutError` for the first turn |
| 35 | the watcher's wait, start to start (mutations) | `assert [datetime.tim...(seconds=271)] == [datetime.tim...(seconds=270)]` |
| 36 | `test_a_backoff_the_previous_run_saved_delays_the_first_search` (the wait removed) | `assert [0.0, 30.0, 60.0, 90.0] == [40.0, 70.0]` |
| 38 | the supervisor over `Work`s | `TypeError: '_RecordedWork' object is not callable` |
| 40 | the floor after a bug (removed; added instead of raced) | `assert [1.0, 2.0, 3....] == [1.0, 61.0, 121.0, 181.0]`; `assert [100.0] == [100.0, 200.0]` |
| 40 | one keyword's bug, Kad's bug (the bug clause narrowed) | 7 failed |
| 40 | a password refused while running (the declared clause narrowed) | `assert [LoggedLine(l...n password'))] == [LoggedLine(l..., error=None)]` |
| 41 | the worker raising after its backoff; the saver's `finally` | `Failed: DID NOT RAISE SearchFailedError`; `assert [] == [{BackoffKey(...annel='kad')}]` |
| 45 | `test_an_answer_trickled_past_the_request_bound_is_an_unreachable_daemon` | `TimeoutError` at the test's 5 s guard |
| 46 | the pacing rules (mutants), the three-run wiring test | `assert [0.0] == [40]`; `assert [0.0, 20.0] == [0, 60]`; `assert [3660.0] == [60]`; `StoreError: database is locked`; `E assert False` |
| 47 | a hung turn; the derived limits; ten keywords on the lock (a limit counting no queue) | `assert [0.0] == [0.0, 90.0, 180.0]`; `assert datetime.timedelta(seconds=300) == ...`; `At index 6 diff: 'keroro 08' != 'keroro 07'` |
| 50 | the pattern under both bands (degraded latched); the supervisor's recording skipped | `assert [<Health.DEGR...>] == [<Health.HEAL...>]`; 5 failed |
| 51 | searches failed; connected to no network (`any` mutated to `all`; the band moved) | `ModuleNotFoundError: ... searches_failed`; `'unknown to failing' != 'unknown to healthy'` |
| 52 | the policy's limit removed; every window emptied; no floor between raising rebuilds; old works not cancelled | `assert [121.0, 242.0...0, 726.0, ...] == [121.0, 242.0, 363.0]`; a second alert; `assert [121.0, 121.0, 121.0] == [121.0, 181.0, 241.0]`; the restart waiting forever |
| 60 | the disk's entry; today's cadence (exit mutated) | `assert [] == [RelayedLogLine(message='download disk low: 1.5 GiB free, ...')]`; `assert [1, 0, 0, 0] == [1, 0, 0, 1]` |
| 65 | a fallen webui logged without an owner | `assert [] == [LoggedLine(level='warning', message='webui, bugs failing: no owner, not restarted', ...)]` |
| 68 | a restart not stopping the old thread; a close stopping nothing | `assert (True, True) == (False, True)`; `assert [<Thread(webu...)>] == []` |
| 70 | the dispatcher's outcomes; the adapter's refusals; the bound on re-entrance (mutation) | `TypeError: ... unexpected keyword argument 'record_outcome'`; `Failed: DID NOT RAISE NotificationRefused`; `assert 5 == 4` |
| 72 | a restart keeping the old notifier; `current_notifier` called once | `assert (6, 0) == (3, 3)`; `assert (2, 0) == (1, 1)` |
| 74 | the services' components; the per-service routing; the services sent to in series (mutation) | `ImportError: cannot import name 'SENDS'`; `TypeError: ... unexpected keyword argument 'service_components'`; `assert 10.0 == 5.0` |

| 90 | a timeout counted by "sends failed"; the condition's name | `assert <Health.HEALTHY: 'healthy'> is <Health.FAILING: 'failing'>`; `('sends refused', ...) != ('sends failed', ...)` |
| 90 | each work named as its component, each owner `owner of ...` (13 tests) | `assert 'status reading of amuled' == 'status sensor amuled'`; `assert 'client amuled' == 'owner of client amuled'` |
| 90 | durations in seconds | `'hung: past its time limit of 0:00:30' != '... of 30 s'`; `'... for 3600.0s: ...' in` |
| 90 | an unreachable client records nothing on "searches failed"; nine unreachable turns | `['channel amu...n to healthy'] == []`; `Left contains one more item: '... failing to healthy'` |
| 90 | a login cancelled in flight | `assert False` (`_ClosingTransport.closed`) |
| 90 | a shielded dispatch, a turn cut between a decision's write and its send, a completion's likewise | `TimeoutError` (three tests, the send never kept) |
| 90 | the works a raising rebuild added stopped before the next attempt | `assert 231.0 < 181.0` |
| 90 | the restart request's surface; the holder; the factories' tests | `ImportError: cannot import name 'RestartRequest'`; `ModuleNotFoundError: ... parts_built_later`; `ImportError: cannot import name 'AmuleWorks'` |
| 90 | `FakeNotifier` under `NotifierContract` | `TypeError: FakeNotifier.__init__() got an unexpected keyword argument 'refusing'` |

Passed at once and kept as guards: block 41's `test_a_refused_password_fails_the_search_and_backs_nothing_off`
(D2), block 47's ten-keywords test (proven by a mutant), block 51's and 65's translator cases, block 60's healthy disk
sending nothing, block 68's restart test (block 52's mechanism), block 74's log line assertion (proven by a mutant).
Block 90's, each proven by a mutant: the give-up then a later bug (MAJOR 1, the reset guarded by `state.phase !=
"given up"`: `assert [] == [<FakeStateOwner ...>]`), the holder's refusal (the `None` check removed: `AttributeError:
'NoneType' object has no attribute 'record'`), the mapping test (the status sensor's component left out of
`AmuleWorks.components()`: the sets differ), `AppriseNotifier` under `NotifierContract` (its behaviour already).
The dispatcher's `:g` for the timeout is held by no test: the tests' timeouts print alike either way. Blocks 33 and
52a add no behaviour.

## Section 4's rows, where each is held

| Row | Test |
|---|---|
| A bug on every Kad search | `test_keyword_search.py::test_a_bug_on_every_kad_search_leaves_the_ed2k_searches_going_on` (blocks 40, 50) |
| A bug on one keyword's searches | `::test_a_bug_on_one_keywords_searches_leaves_the_other_keywords_searching`; `test_a_bug_on_one_keyword_s_searches_restarts_its_client_three_times_at_most` (block 52) |
| A unit of work past its maximum duration | `test_a_turn_past_its_time_limit_is_cut_as_a_bug_and_its_work_goes_on` (block 47), recorded from block 50 |
| A bugs condition failing with no recovery | `test_a_bugs_condition_failing_restarts_its_owner_three_times_then_never` (restarts at 121, 242, 363 s) |
| aMule unreachable | `test_amule_unreachable_fails_the_client_s_condition_and_restarts_nothing` (block 52) |
| The pattern `000111000111` then ten successes | `test_health_condition.py` (block 20, again with both bands in block 50) |
| The connectivity alerts | the status sensor's and the translator's tests (blocks 20 to 27) |
| Two status fields of one channel | block 27 (only the connectable alert, at the sixth reading) |
| An unknown reading between two failed runs | block 25 |
| A client restart under an open connectivity alert | `test_a_client_restart_under_an_open_alert_neither_sends_it_again_nor_ends_it` (block 52) |
| A work raising a bug at once, turn after turn | the floor tests of `test_supervisor.py` (block 40) |
| A rebuild of the client that raises | `test_a_rebuild_that_raises_records_a_bug_on_each_component_and_is_tried_after_the_floor`, `test_three_raising_rebuilds_give_the_owner_up_its_works_stopped_the_node_running` (block 52) |
| A password refused while the node runs | `test_a_password_refused_while_the_node_runs_is_a_declared_outcome_each_turn` (block 40) |
| Ten eD2k keywords queued on the client's lock | `test_ten_keywords_queued_on_the_clients_ed2k_lock_stay_within_their_time_limits` (block 47) |
| A channel backed off when the node restarts | `test_a_backoff_the_previous_run_saved_delays_the_first_search` (block 36) |
| A client rebuilt, or the node restarted, within a minute of a search start | `test_a_search_start_the_previous_run_wrote_holds_the_ed2k_search` and the three-run wiring test (block 46) |

## Accepted limits

The spec's section 6, its D20 limit narrowed by the closing block (a restart or a time limit no longer loses a
notification, the process's death still does) and its no-owner limit removed with its branch; and what the operator
accepted during Wrap, quoted (`lot4b-operator-answers.md`, 21 to 25):

- **After three useless restarts whose rebuilds succeeded, the owner's works run on**, only the buggy turns failing,
  the count reset once every bugs condition of its components is healthy again, so a later bug gets three restarts
  more; after three rebuilds that raised, nothing of the owner's work runs until the container restarts (answer 21):
  "A".
- **A notification is lost only if the process dies between its write and its send**: a restart or a time limit
  cancelling the turn leaves the sends to their end within their timeout (answer 22): "A".
- **A timeout counts toward a service's condition as a refusal does** (answer 23): "Aligné avec la reco, on ne gagne
  pas à distinguer."
- **Source tracking's failed list read waits a full `sources_interval`** (block 35, answer 24), a fixed cadence: "On
  garde A".
- **The choices made in blocks**: block 51's "connected to no network" at 6 of 6 (the lead's answer on its pull
  request), block 68's webui rebuild whose bind fails not raising (a port held elsewhere costs three useless restarts),
  block 70's source covering a notification's send, block 74's `NOMATCH` a refusal logged at each send, block 47's
  teammate editing the spec's formulas and the yield's row, block 52 at 21 files (answer 25): "ça me semble ok".
- **The list of declared failures is written by hand** (the lead's, holistic MINOR 14):
  `test_every_failure_a_driven_port_declares_is_a_declared_failure` misses a new port's failure until someone adds
  it; a check over the ports' docstrings would parse prose.

## Found by the blocks, for the operator

Each with its block and its exit; none is an accepted limit unless the list above says so.

- **An unreachable reading samples every channel as unknown, at boot too** (block 25): two debug lines at a boot with
  the API down, no gauge series either way. Not a review finding; left as is.
- **A failed list read waits a full interval** (block 35): accepted, answer 24.
- **A login cancelled during a rebuild left its httpx client unclosed** (block 52): fixed by block 90 (holistic MINOR
  2), the client closed on any exit of the login.
- **A webui rebuild whose bind fails does not raise** (block 68): accepted, answer 25.
- **A `TimeoutError` the notifier raises itself is recorded as `NotificationTimedOut`** (block 70): `asyncio.wait_for`
  cannot tell it from its own expiry. Not a review finding; left as is.
- **A send in flight during a restart finishes on the old notifier; a restarted notifier stays unknown until its
  third send** (block 72), a useless restart noticed at the third bug after it. Not a review finding; left as is.
- **A notification service that only times out never failed** (block 74): fixed by block 90 (holistic MAJOR 2,
  answer 23). A bug on one service rebuilds every service's apprise objects, and two alike URLs reordered swap their
  names: not review findings; left as is.
- **A spacing lost to a store failure costs one early start** (block 46): the spec's settled row.
- **A turn past its limit is logged without its trace** (block 47): the spec's sketch; the trace would show where the
  cancellation landed, not why the turn was slow.

## The holistic review's findings and their exits

`.reviews/v5-lot4b-holistic.md`: 0 CRITICAL, 5 MAJOR, 18 MINOR; the exits settled by the lead and the operator.

| # | Finding | Exit |
|---|---|---|
| MAJOR 1 | after three useless restarts whose rebuilds succeeded, the works run on and the count resets, unseen and untested | fixed: the code kept (answer 21), the spec's step 4 says both cases, a test of a give-up then all healthy then a bug |
| MAJOR 2 | a service that only times out reads healthy | fixed (answer 23): "sends failed" counts `NotificationFailed`, a refusal or a timeout |
| MAJOR 3 | a restart or a time limit cancelling a turn loses a notification | fixed (answer 22): `dispatch_shielded` after a decision's write and a completion's; D20's limit unchanged |
| MAJOR 4 | no test runs D5 as the node wires it | fixed: `AmuleWorks`, `WebuiWorks`, `component_owners`, `apprise_notifier` with tests of their own; a real restart left to the release candidate |
| MAJOR 5 | the draft's "Accepted limits" held teammates' findings | fixed: this handoff's two lists above |
| MINOR 1 | the old works stopped once, before the retry loop | fixed: stopped before each attempt |
| MINOR 2 | a cancelled login leaves its httpx client unclosed | fixed: closed on any exit of the login |
| MINOR 3 | the no-owner branch had no production user | fixed: deleted with its test, section 6's limit removed |
| MINOR 4 | "searches failed" healed during an aMule outage | fixed: a search turn records a success or a refusal only |
| MINOR 5 | choices made in blocks the operator never saw | fixed: marked in the spec with answers 24 and 25 |
| MINOR 6 | one part, two names in the log; `TURNS` two concepts | fixed: each work named as its component, each owner `owner of ...`, `UNITS_OF_WORK` |
| MINOR 7 | `_last_turn_ended_at` | fixed: `_latest_turn_ended_at` |
| MINOR 8 | "apprise groups", "Never raises", `WorkAdder`'s home | fixed |
| MINOR 9 | `architecture.md`'s "boucles" and its old alert end | fixed |
| MINOR 10 | section 6 lacked lot 4b's operator-visible changes; `operate.md` contradicted | fixed: section 6 gains them, `operate.md`'s sentence corrected |
| MINOR 11 | no `NotifierContract` | fixed: `AppriseNotifier` and `FakeNotifier` run it, four doubles exempted with their reasons |
| MINOR 12 | three duration formats | fixed: `{seconds:g} s` everywhere, `troubleshooting.md` corrected |
| MINOR 13 | the restart's sequence over four public methods; names bound later read by lambdas | fixed: `RestartRequest`, `PartsBuiltLater` |
| MINOR 14 | TDD departures; the hand-written list of declared failures | the departures named under "Departures" and "The tests watched failing"; the list an accepted limit, the lead's |
| MINOR 15 | the spec's table lacked 27, 35, 41, 52a; `StatusLoop`; block 52's files | fixed: rows added, the name corrected, block 52's 21 files accepted (answer 25) |
| MINOR 16 | block 36 touched lot 7's guide, block 40's hunk dropped | the rule stated once in section 6 "For lot 7"; no revert |
| MINOR 17 | four CI runs stuck queued | the lead's, in Integrate: the rebase onto `main` must show a green run on each of the four branches |
| MINOR 18 | docstrings past two lines; "D9's mark" as a reason | fixed |

The TDD departures the review named (MINOR 14): block 74's log-line assertion written after the code, proven by a
mutant; block 68's restart test passing at once; block 30's four wait tests and block 35's failing only on a
constructor `TypeError`; block 36's evidence mutations of code already written.

## For lot 7 (the operator pages, umbrella D19)

The spec's section 6 lists what the pages must say. The blocks add, each a line the operator now reads:

- **The health log** under `p2pwatch.application.steps.health_recorder`, one line per transition, a warning into
  degraded or failing, an info otherwise: `client amuled, unreachable: ...`, `channel amuled kad, not connectable:
  unknown to degraded`, `channel amuled kad, searches failed: unknown to failing`, `download tracking amuled, connected
  to no network: unknown to failing`, `download tracking amuled, disk space low: unknown to degraded`, `search 'keroro'
  amuled kad, bugs: unknown to failing`, `notifier discord community, sends failed: unknown to failing`; one info
  `..., unknown to healthy` per condition once its window fills after a start (blocks 20 to 74).
- **The supervisor's lines**: a bug no longer stops the node, `bug in <work>` (error, with its trace), its next turn
  at least 60 s later; a declared failure `<work>: <reason>` (warning); a turn past its limit `<work>: past its time
  limit of 1200 s` (error), every duration in seconds (blocks 40, 47, 90). Each work is named as the component it
  feeds: `status sensor amuled`, `search 'keroro' amuled kad`, `download tracking amuled`, `source tracking amuled`,
  `webui` (block 90).
- **A failed search is logged twice**: the worker's line as before, then the supervisor's `search '<keyword>' <client>
  <channel>: <reason>` (blocks 41, 90).
- **A password refused while the node runs no longer stops it**: a warning each status turn, nothing alerted until
  lot 4c's block 73 (block 40, the spec's limit).
- **Source tracking**: no more `download sources store failure (...): step skipped, retry` (the supervisor's warning
  replaces it, block 40); its reads start to start (block 35, `docs/settings.md` updated).
- **The restarts** under `...restart_policy` and `...supervisor`: `search 'keroro' amuled kad, bugs failing:
  restarting owner of client amuled` (warning), `owner of client amuled restarted` (info), `restart of owner of client
  amuled raised` (error, with its trace), `owner of client amuled: 3 useless restarts, its components failing; not
  restarted again` (error); the same for `owner of the webui` (then `webui serving on <host>:<port> (own thread)`) and
  `owner of the notifier` (`notifier discord community, bugs failing: restarting owner of the notifier`); the
  shutdown's stderr line now reads `amuled session closing…` (blocks 52, 68, 72, 74, 90).
- **A fallen webui**: `bug in webui` (error, the `WebuiFallen` trace) each minute, the thread's own line
  `webui degraded: the crawler carries on without HTTP` carrying the cause, then the restart (blocks 65, 68).
- **The notifications**: `notification <audience> failed (<error>)` is gone; in its place, per service,
  `notifier discord community: refused (FAILURE)` and `notifier discord community: past its timeout of 5 s`
  (warnings), `bug in notifier discord community` (error, with its trace); a service that only times out fails its
  "sends failed" (block 90); a refusal by a service (a webhook's
  4xx) is now logged; a URL apprise cannot load is a refusal at each send, logged, where it was skipped in silence;
  with several URLs for one audience a notification waits for the slowest, within the timeout; without any URL there
  is no notifier component (blocks 70, 74).
- **The search starts survive a restart**: the `latest_search_starts` table, and a node restarted within a minute of a
  search holding that channel's first search until the spacing ends (block 46, in the spec's section 6); the store's
  two error lines `latest search starts not read (...): the first starts not spaced` and `search start not written
  (...): a client built anew may start early`.
- **A stalled amuleapi reads as an unreachable client after 60 s** (block 45), through the existing path.
- **A loss line in seconds**: `file=... unseen by the client for 86400 s: marked failed` (block 90,
  `docs/troubleshooting.md` corrected); `operate.md`'s sentence on an unreachable API corrected (block 90): the
  channels keep their last readings, no channel alert starts or ends.
- `docs/migration-4x.md` is lot 7's: block 36 corrected a sentence it made false, block 40's new hunk was dropped, the
  rule stated once in the spec's section 6. The operator's line `download enabled: download loop armed` keeps its
  words. Section 6 "For lot 7" now lists all of the above (block 90).

## The operator's decisions outside the blocks

From the lead's record of 2026-11-11 and 2026-11-12, the operator's words quoted:

- The wait between two turns, what a success counts for, what publishes the transitions: "A", "A", then "ok" to "un
  standard central".
- How a work knows the node id: "A, mais on uniformise avec les autres choses qui en avaient besoin et qui le passaient
  en paramètre".
- A rebuild that fails, the download split: "A", "A".
- The stack's size: "Je préfère un seul lot".
- A turn growing with live counts: "Concrètement, sur un crawler à la recherche de lost media le nombre de
  téléchargements est par définition faible. Je pense que ça peut être une limite acceptée."
- The transitional code: "On fusionne les paires de blocs"; for blocks 30 to 39, "les deux me semblent pas super. On a
  pas moyen de faire mieux ?", then "Ok" to the third order (the preparation, the swap, the behaviour).
- A reader of health in lot 4b, the rebuild that raises (put a second time in plain words): "A", "A".
- Which failures derive from `DeclaredFailure`: "Oui" (D3 whole).
- "Searches failed", "connected to no network" and "sends refused" back in lot 4b: "ok".
- The glossary's `step` line, block 40 at 29 files: "recos ok".
- Why the latest starts are keyed by client: "2 clients sur la même IP (avec nécessairement des ports différents)
  sont comptés différemment, mais un 3e compte comme un acteur malicieux. Il y a une limite de-facto à 2 clients par
  IP. p2pwatch n'en utilise qu'un, et c'est bien car ça laisse l'utilisateur libre d'avoir un amule à part aussi."
- Block 46's spec correction and its size: "approuvé".
- Block 52 at 1510 lines, 52a split off: "reco ok".
- The holistic review's exits, during Wrap (answers 21 to 25, quoted under "Accepted limits"): "A", "A", "Aligné avec
  la reco, on ne gagne pas à distinguer.", "On garde A", "ça me semble ok".

## The lot's counts

The lead's record, and the reports:

- Blocks: 26 with the closing one (the spec's 22 rows, block 46 added, four splits), the closing block in 8 steps
  under both bounds, for the lead to cut.
- Fix-backs: 1 (block 51's band, after its pull request, nothing stacked above). Cascaded rebases: 0. Runs
  re-triggered: 2 (block 74's first run cancelled by the handoff's push; block 52's push at 52a's insertion). Rebases
  onto `main`: 0 so far. Fewer runs re-triggered than blocks.
- Splits: 4 (25/27, 33/34, 40/41, 52a out of 52). Blocks inserted: 1 (46) plus 52a. Bounds passed with the operator's
  acceptance: 10, 20, 40, 46, 52.
- Class 2 questions: 1 (block 45, answer 17). The operator's answers, verbatim: "On ne peut pas résoudre ça simplement
  en stockant dans local.db la date et heure de dernier lancement ? Ça résoudrait les deux cas sans problème.", then
  "ça me semble ok, mais gardons en tête que ça doit être générique pour généraliser ça à d'autres réseaux p2p (v5) et
  donc clients."
- Bodies the operator called unreadable unprompted: 0.
- Changes after a pull request opened, seen in the reports: block 51's band moved from 3 of 3 to 6 of 6 on the lead's
  answer; block 40's `docs/migration-4x.md` hunk dropped on the lead's request. The stack re-created as GitHub stack
  #740 for 52a's insertion.
- Continuous integration: four runs, of blocks 20, 25, 27 and 30, stuck queued on GitHub with no job since 2026-11-11,
  each block green locally (the rebase onto `main` must show each green, holistic MINOR 17); the GitHub REST quota
  exhausted once on 2026-11-11 by parallel `gh run watch` calls.
- Class 1 fixes: 7. Block 20: `ClientUnreachableLasting`'s comment ("emitted once until one comes" now "until it
  heals"). Block 38: the composition's docstring named download tracking's work alone. Block 47: the eD2k search's and
  the Kad search's formulas (`S + B + 3c`, `2B + 4c`). Block 60: `events.py`'s docstring and `test_policy.py` named a
  `first_occurrence` no event carries. Block 68: `_start_webui`'s unread `run_state_store` parameter. Block 70: the
  adapter's docstring said apprise with no service returns `None` (2.1 answers `NOMATCH`). Block 72:
  `docs/contributing/architecture.md`'s module table lacked `webui_thread_owner.py`.
- Gates: the crawler from 2791 tests passed (block 10) to 3038 (block 74), then 3055 (block 90), 4 skipped, 21
  deselected throughout.

## Pitfalls learned

- **Serena**: `rename_symbol` also rewrites `agents/reference/`'s dated probes (block 30, reverted); a block 33 rename
  from `DownloadCycle/run` missed a docstring's double-backticked name; confirm with `git grep -n -w` and
  `git diff --word-diff`.
- **`sed` line-number insertions shift after the first one in a file** (block 10); the `TypeError` run caught the two
  constructions missed.
- **git's rename detection decides a block's measure**: a test module rewritten below 50 % similarity counts every
  line twice (block 36, 814 lines in one commit, 469 in two).
- **Python 3.13 evaluates annotations at definition**: `Self` and a quoted `"Component"` (block 20).
- **The core's import rules**: `from abc import ...` needed `application-imports.yml` (block 30); `asyncio.gather` is
  not allowed, `TaskGroup`, `Queue`, `Task`, `wait_for` are (blocks 40, 52, 74); `asyncio.timeout` is refused in the
  core (block 47's race on `MonotonicClock.sleep`), allowed in the adapters (block 45).
- **`PLR0917`**: a private method's second parameter goes keyword-only (block 74).
- **On the virtual-time loop**: a work whose wait is zero and whose turn raises at once spins without the floor, so a
  floor test gives the work a 1 s wait (block 40); `VirtualLoop` refuses any real I/O, so a trickling socket runs on
  the real loop with sub-second bounds (block 45); with `FakeTime`'s instant sleeps every limit expires at once, so
  the supervisor tests use `FakeBlockingMonotonicClock` (block 47); a bound raced against `FakeTime`'s sleep would win
  every race (block 45).
- **A mutation making a wait return at once leaves a cancellation test spinning forever**: run mutations under
  `timeout`, deselect that test (block 34); a supervisor test awaiting a work's `started` event hangs rather than
  fails when the work never starts (block 38).
- **A mutation of the same size saved within the same second keeps a stale `.pyc`** (CPython checks the mtime in
  seconds and the size): delete the `__pycache__` file (block 51).
- **`git checkout <sha> -- .` restores changed files but does not delete those the commit removed** (block 34).
- **A turn run in a task of its own breaks the wait and the turn's atomicity**, on which `KeywordSearch`'s backoff
  check rests: the turn stays in the waiting task (block 47).
- **Recording inside a turn and after it differ**: the supervisor records a turn's outcome in the work's task, outside
  the limit, so a raising subscriber there ends the node, which is why the restart runs in a task of the supervisor
  (block 50); `KeywordSearch` records on its channel inside the turn, so a raising subscriber there is a bug of that
  turn (block 51).
- **Build order in the composition**: the recorder's subscribers include the restart policy, which needs every owned
  component, so any step that records is built after the recorder and its components before the policy (block 60); a
  name a nested function reads must be bound before its first call, and mypy cannot type one read before its
  assignment (blocks 52a, 52); the parts built before the recorder and the supervisor reach them through
  `PartsBuiltLater`, a read before either is set a `PartNotBuiltYetError`, never a `NameError` (block 90).
- **The supervisor empties the bugs windows right after `restart()` returns**: an owner that awaited after adding a
  work could see its first outcome erased; `AmuleClientOwner` adds its works last (block 52).
- **Recording nests**: the notifier's transition reaches every subscriber before the subscribers after the translator
  receive the outer one; lot 4c's alerts on the notifier's components must not be sent through the notifier, or the
  bound on re-entrance breaks (block 70). Each service's outcomes are recorded after every send of the notification
  has ended (block 74).
- **Two works no longer prove each other's writes**: a listing after a sources read does not prove the read's points
  were written; wait for a request from the same work (block 35).
- **`BackoffSaver.saving()` saves when a turn is cancelled too**, a synchronous write in its `finally` (block 41).
- **`lasting_at_entry` unpacks a single band**: it raises on a two-band condition; only the translator calls it, for
  the reading conditions (block 50).
- **`Work.__str__` and `StateOwner.__str__` are abstract**: every work, owner and test double names itself (blocks 40,
  52).
- **`is_alive()` right after a failed bind can read true for an instant**, the thread setting its event in its
  `finally` (block 65); `test_a_restart_stops_the_old_thread_and_serves_on_a_new_one` counts the process's threads
  named `webui`, so a leak elsewhere fails it (block 68).
- **`FakeAmuleApi` keeps only its `FakeTime`'s monotonic clock**: tests outside the pacing module hand the client a wall
  clock of another `FakeTime`, harmless where no test checks pacing (block 46).
- **The notifier's components are built from the services the first notifier lists**: a rebuilt notifier must list
  equal services, which the same configuration guarantees (block 74). `FakeNotifier.calls` keeps
  `(audience, notification)`; a test needing the service reads the outcomes on its components.
- **The policy indexes its owners directly** (block 90): a component carrying a bugs condition without an owner is a
  `KeyError` in the recorder's subscriber, which a supervisor's recording turns into the node's end. Every component
  the composition builds is owned through `component_owners`; a test building a policy over part of its components
  subscribes it only when it restarts (`test_keyword_search.py`) or gives the others an owner of their own
  (`test_supervisor.py`).
- **A shielded send outlives its turn** (block 90): `dispatch_shielded` holds its task in the dispatcher, the loop
  keeping a weak reference to a task alone; at the shutdown a send in flight goes on within its timeout while the
  resources close.
- **Serena's index can be stale at a block's start** (block 90): its references came back at shifted lines, so the
  renames of constants went by `git grep -w`; check the index on a recent name before the first rename.
- **An index already holding a restore** (`git checkout <ref> -- <paths>` stages them): a later `git add` of a few
  files commits them all (block 90, caught by `git show --stat`).

## Not validated

- **No restart ran through the real composition** (blocks 52, 68, 72): the works' factories and the mapping of
  components to owners have tests of their own since block 90 (every feed owned, each owner's components those its
  works feed, a rebuilt client's turns on the new client), but a real restart on the node, the webui's liveness
  reaching its first turn in a wiring test (block 65) and the order the composition builds its parts in are left to the
  release candidate's fault injection.
- **Integration suites**: block 46 ran `api_integration` and `download_integration` against
  `ghcr.io/mission-titar/p2pwatch-amule:latest` on `-p 14711:4711`, 5 passed; the compose smoke test was not run (its
  changed script only parsed with `ast.parse`); block 45's integration constructions only gain an argument, not run.
- **Nothing ran against a real node**: the conditions' log lines and their cadence (a channel refused, a dip below the
  disk floor), the restarts and their log lines, a rebuilt client's searches, a webui fallen then served again, a real
  apprise notifier rebuilt, a real webhook refusing (a Discord 4xx), two services of one audience, the time limits
  against a real aMule, a turn cut in production, the order of the first search start and the first status reading
  on one session (block 36), source tracking's cadence (12 rounds an hour at the shipped 300 s, block 35).
- **The order "before the webui"** of the node id's resolution has no test of its own (block 10).

## Next step

The lead cuts block 90's steps into branches on top of the stack, then rebases the whole stack onto `main`, each of
the four branches whose runs stuck queued showing a green run (holistic MINOR 17); the operator reads and merges the
stack. No release: v5 ships after lots 4 to 7 and the release candidates. Lot 4c next, what the operator sees and the
real stops (its 18 blocks, from 05, `feat/health-graph`: `Dependency`, `Quorum.ALL`, the propagation, the health
gauges its first reader), on the conditions and components this lot built; its alerts on the notifier's components
must not be sent through the notifier (block 70's pitfall).

# Handoff: v5 lot 4b6, the health model redrawn (tier Spec)

Drafted by block 65's teammate from the block reports (#808 to #833, the collapsed "Block report" of each pull request
body) and its own; corrected by the closing block from the reports of #834 to #840 and the holistic review
(`.reviews/v5-lot4b6-holistic.md`, below). Spec: `agents/specs/2026-11-18-v5-lot-4b6-health-model-redrawn.md`,
decisions D20 to D34, which replace the lot 4b spec's D1, D4, D6 and D14 to D16. Once this stack has merged, lot 4c's
spec is rewritten on this lot's names.

## Current state

- **Two causes, two answers** (D20, D21). A bug is our code's: anything a turn raises but an `ExpectedError`. The
  supervisor counts it on the work that met it and rebuilds that work's object. An outage is outside the program: a
  rule of an external dependency failing, which the node's health logs and alerts on. No log line says a part has
  bugs.
- **`ExternalDependency`** (`domain/health/external_dependency.py`, `Component` renamed) is what the node depends on
  and does not control: `client amuled` (unreachable, connected to no network, password refused), `channel amuled
  ed2k` and `channel amuled kad` (not connected, not connectable, searches failed), `download disk` (disk space low, on
  a node that downloads), `local database` (saves failed) and each `notifier <service>` (sends failed). Its `rules` map
  each rule to its `HealthAlert` or `None`; a `HealthTransition` carries its rule's alert, and `alert_event()` gives the
  alert, its end, or nothing for a rule healthy from its first checks. Each builder (`client_dependency`,
  `channel_dependency`, `download_disk_dependency`, `local_database_dependency`,
  `notification_service_dependencies`) builds its alerts from the node's id and, for the disk, its floor. No alert
  names a service's rule: it would go through that service. `state()`, `HealthTransition.dependency` and `.rule` are
  gone, read by no source since the restart policy and the health alerter went.
- **`NodeHealth`** (`application/steps/node_health.py`) tracks the outages alone: `record(on=..., rule=...,
  detected=...)` logs each change and dispatches its rule's alert, nothing awaited before the entry is left. Every step
  that records takes it, the notifier's work included. The health alerter, its `_RULES_WITHOUT_AN_ALERT` and
  `HealthSubscriberBuiltLater` are gone: the dispatcher is built first, since it needs only the outbox.
- **Every notification goes through `NotificationOutbox`** (`application/steps/notification_outbox.py`): the
  dispatcher plans, logs, writes the metrics, then `leave`s one `PendingNotification` per service of its audience,
  without awaiting anything, and wakes `WakeSubject.NOTIFICATION`; an audience without a service leaves nothing and
  saves nothing. The notifier's rebuild hands back one `NotificationSender` per service (`notification sending
  discord community` in the log), so that a service that never answers holds no other: each turn sends the oldest
  entry left for its service within `notification_timeout_seconds`, records "sends failed" on its service and "saves
  failed" on the local database, and removes the entry once its send has ended (sent, refused, past its timeout, or
  met a bug, a bug of its turn); a cancelled send keeps its entry. At the shutdown, `empty_the_outbox(senders)` has
  each sender send what is left for its service, all at once, again while a send left another, through a notifier the
  composition built for the lifecycle at the start, within the shutdown bound. `dispatch_shielded`, `finish_shielded_dispatches`,
  `CurrentNotifier` and the notification timeout in `AmuleWorkTimeLimits` are gone.
- **The outbox is saved in `local.db`** at each change (`NotificationOutboxWriter.set_pending_notifications`,
  `NotificationOutboxReader.read_pending_notifications`, one adapter, `SqliteNotificationOutboxStore`, table
  `pending_notifications`, migration `local/0017`), the four kinds of notification in a JSON object under `kind`. It
  reads itself back in its constructor: an entry it cannot read back (`UnreadableNotification`, such as a row an
  earlier version left without a field added since) or for a service no longer configured is dropped in one warning
  line; a read the database refuses still stops the start. It sends from memory whatever the database: a refused
  save is one warning, and the outbox keeps whether its latest save failed, which each sender records at each turn.
- **Each object the node can rebuild is built whole** (`Restartable`: `works()`, `close()`; `RestartableBuilder`:
  `build()`, the first included): the aMule client (`composition/amule_client_restartable.py`), the webui
  (`webui_restartable.py`), the notifier (`notifier_restartable.py`). The client's channels (`CHANNELS`) and the
  request bound are known before any client is built.
- **The supervisor alone decides each rebuild and runs it** (`application/steps/supervisor.py`, D32). `build_first`
  builds each object and keeps it in a `_SupervisedObject`, private to it; `supervise()` runs the works of the
  objects it built, and only those. Each work is judged on its own turns by `BUGS` (failing at 3 bugs in a row, healthy
  again once fewer than 2 of its last 10 met one, unknown before its third turn), kept across a rebuild under the
  work's name in the log. A work turning failing stops its object's works; after 1, 2, then 4 minutes (in memory, on
  the monotonic clock) the object is closed, rebuilt, and its new works run. A rebuild is in vain when a work of the
  object meets 3 bugs in a row after it, or when it raises (an outage included, as the lot 4b spec's D15 has it); the
  count resets once every work of it that turned failing is healthy again. While a rebuild is under way, the old
  works' last turns decide nothing.
- **The third rebuild in vain leaves the object unrepaired** (D33): rebuilt no more until its count resets, its works
  running on, the failing ones failing alone. The supervisor dispatches `WorksStillFailing`, `client amuled: search
  'keroro' amuled ed2k still failing after 3 rebuilds: a bug of its own, or a shared state a crawler restart would
  renew` (operations), and at the reset `WorksHealthyAgain`, `client amuled: every work healthy again`.
- **A function wholly lost restarts the crawler** (D34). Each `SupervisedWork` serves a `CrawlerFunction`
  (`domain/crawler_function.py`): the webui (its thread watch), the notifications (each service's sending), the crawl
  (every client's searches), and on a node that downloads the downloads (download and source tracking); the status
  reading serves none. A function is lost when every object serving it is unrepaired and every one of its works is
  failing, a work that never turned not failing, an object whose third rebuild raised holding no work and counting as
  failing. `supervise()` then cancels every work and raises `CrawlerRestartError` (`the crawl lost after 3
  rebuilds`); the lifecycle dispatches `CrawlerFunctionLost` (`the crawl lost: every search failing after 3 rebuilds:
  the crawler restarts`), empties the outbox and raises; the composition closes every object and both databases
  within the shutdown bound, a deadline cutting the drain or the close keeping the restart's error; the command line
  prints `Exiting for a restart: the crawl lost after 3 rebuilds` and exits 1, and `restart: unless-stopped` has
  Docker start the crawler again, `amuled` untouched. Each work checks the run state before each turn.
- **Download tracking is no dependency any more**: "disk space low" is the download disk's, "connected to no network"
  the client's, recorded at every answered reading, downloading or not.
- **A refused password is an outage of amuled** (D24): "password refused", failing at one refusal, healthy again at
  the first answered reading, recorded by the status reading alone; alert `amuled refuses the password: check the
  configuration`, end `amuled accepts the password again`. The client tolerates it at its login, at the node's start
  and at a rebuild, as it tolerates an amuled not listening yet. After a refused login, every call raises
  `ClientAuthError` at once, without asking amuleapi, until the next login, 1 min later, doubled at each refusal, 30
  min at most; an accepted login brings the wait back to 1 min (`AmuleApiClient._refuse_while_the_login_waits`).

## Accepted limits

The spec's section 6, each reached by this lot:

- **An unrepaired object waits for the operator**: a work three rebuilds did not repair runs on failing, an alert
  naming it, until it is healthy again or the operator restarts the crawler.
- **A notifier unrepaired on its operations service alerts no one**: its alert goes through that failing service; the
  community service, healthy or idle, keeps the notifications from being lost, so the crawler runs on; the log keeps
  the alert.
- **A node whose cause survives its own restart restarts without end**, an alert at each round, until the operator
  steps in (the operator, 2026-11-18): each round 7 minutes of waits plus the twelve bugs that turn the works failing
  four times, 60 s apart at least, 904 s for a search meeting a bug at every turn.
- **A notification can be sent twice** when the node stops between its send and the save of its removal.
- **A notification is lost when the process is killed** between a decision's write and the save of its entry, or
  before its save when `local.db` cannot be written.
- **A notification refused by its service, or whose send met a bug, is lost.**
- **A kept entry goes to the service that bears its name at the start**: two URLs of one scheme and audience swapped
  between two runs swap their entries.
- **When the notifier's bug survives the restart, its alerts never go out**; the log keeps them.
- **A rule that no code records stays unknown, and nothing says so.**
- **An entry the start cannot read back is dropped** in one warning line: a notification an earlier version saved
  without a field added since is lost (the holistic review, block 80).
- **A burst of n notifications writes about n²/2 rows**: the outbox saves its whole table at each change (the holistic
  review; a comment in `NotificationOutbox._save`).

## What was built, block by block

| # | PR | Branch | Block | Lines, files |
|---|---|---|---|---|
| 5 | #808 | `test/todays-alerts-held` | today's alerts held by a test, the spec and the reading guide | 221, 3 |
| 10 | #809 | `refactor/external-dependencies` | `Component` renamed `ExternalDependency`, `outage` in the glossary | 448, 51, accepted |
| 13 | #811 | `test/steps-read-handed-on-notifications` | the steps' tests read the notifications their dispatcher hands on | 46, 10 |
| 15 | #812 | `refactor/notifications-through-the-outbox` | the outbox in memory, the notifier's work sending from it | 1 542, 31, accepted |
| 20 | #814 | `refactor/shielded-sends-removed` | the shielded sends removed | 213, 18 |
| 23 | #815 | `refactor/no-notification-timeout-in-time-limits` | no notification timeout in the turns' limits | 37, 7 |
| 25 | #816 | `feat/outbox-saved` | the outbox saved in `local.db`, read back at the start | 913, 22, accepted |
| 27 | #817 | `feat/local-database-outage` | the local database an outage, its alert sent from memory | 249, 18 |
| 28 | #821 | `refactor/channels-known-before-the-client` | the client's channels and request bound known before any client | 15, 3 |
| 30 | #822 | `refactor/client-built-whole` | each object built whole by its builder, the supervisor keeping the latest (block 35 merged in) | 1 034, 29, accepted |
| 37 | #824 | `refactor/supervisor-runs-its-objects-works` | the supervisor runs the works of the objects it built | 201, 12 |
| 40 | #825 | `refactor/supervisor-counts-the-bugs` | the bugs counted per object, the restart policy and the bugs rule removed | 1 846, 40, accepted |
| 45 | #827 | `feat/rebuild-waits` | each rebuild waits 1, then 2, then 4 min | 76, 7 |
| 50 | #828 | `feat/crawler-restart-past-three` | the third rebuild in vain restarts the crawler, its alert sent first | 263, 17 |
| 53 | #829 | `refactor/download-tracking-split` | download tracking split | 161, 17 |
| 55 | #830 | `refactor/rules-carry-their-alerts` | each rule carrying its alert, the node's health dispatching it | 1 012, 30, accepted |
| 60 | #832 | `feat/password-refused-outage` | the refused password an outage of amuled, with its alert | 143, 9 |
| 65 | #833 | `feat/login-tried-again` | the login tried again after waits that double, a refused password tolerated at the start | 247, 9 |
| 70 | #834 | `feat/works-judged-alone` | each work judged on its own turns, kept across a rebuild (D32) | 190, 6 |
| 72 | #835 | `feat/function-lost-restarts-the-crawler` | an object left unrepaired, each work's function, the crawler restarted when a function is lost (D33, D34) | 364, 28, accepted |
| 74 | #836 | `feat/unrepaired-object-alert` | the alert of an object left unrepaired, and its end | 205, 13 |
| 75 | #838 | `fix/one-sending-per-service` | one notifier's work per service | 443, 12 |
| 80 | #839 | `fix/lot-4b6-review-fixes` | the holistic review's behaviour fixes | 283, 15 |
| 82 | #840 | `refactor/lot-4b6-review-words` | the holistic review's words, the surface nothing reads removed | 204, 17 |
| 90 | | `docs/lot-4b6-wrap` | closing block: this handoff, the spec's corrections, `BACKLOG.md` | 4, 1 |

- **25 blocks, past the workflow's 19**, accepted by the operator on 2026-11-21. The lot as a whole: 117 files, +5 592
  / -3 883 outside the dated directories (`git diff --shortstat origin/main...HEAD`, 2026-11-21).
- **Past a bound, accepted by the operator**: 10 on its row of the spec (a rename); 15 at 1 542 lines and 31 files,
  block 13 cut out first (2026-11-18); 25 at 913 lines and 22 files, block 27 cut out (2026-11-19); 30 at 1 034
  lines and 29 files, block 35 merged in, block 28 cut out ("A", 2026-11-20); 40 at 1 846 lines and 40 files, about
  1 100 removed, block 37 cut out (2026-11-20); 55 at 1 012 lines and 30 files, 683 removed, block 53 cut out
  (2026-11-21); 72 at 28 files, 15 of them the required `function` field at every site (2026-11-21).
- **Cut by the lead within a bound**: 5 out of 10 (663 lines with the test); 23 out of 20 at the commit boundary (25
  files together); 70 into 70, 72 and 74 (686 lines, 29 files as three commits); 80 into 80 and 82 by theme (487
  lines, 26 files as one branch of 7 commits).
- **Block 50's first draft** (the run state carrying the error, the supervisor requesting the shutdown) measured 416
  lines and 24 files; the operator chose that the supervisor ends its own supervision and the lifecycle dispatches the
  alert (spec corrected in `c7f9d6c9`); the draft's commits were dropped and rewritten.
- **Blocks 70 to 74 answer the review's two MAJOR findings**, settled with the operator as D32 to D34 on 2026-11-21;
  block 75 its MINOR on one work over every service; blocks 80 and 82 every other MINOR.
- **Departures, per block**:
  - **5**: the test is `tests/application/test_health_alerts.py`, testing no single module, hence its
    `tests_without_unit` entry. Later blocks change only its setup (`_status_alerts`, `_disk_alerts`): 55 builds it
    without the alerter, every case and assertion unchanged.
  - **10**: every log text kept (`client amuled, unreachable: ...`); the four parts holding the bugs rule alone carry
    the new name until block 40. The ast-grep rule over the record is `external-dependency-record-through-node-health`.
  - **15**: one work over every service (one per service from block 75); the bug's line is the supervisor's; the
    shutdown's last sends go through a notifier the lifecycle builds at the start; the outbox waits through the
    `Waker` port; no service configured, no work. The dispatcher takes a `leave_notification` callback
    (`outbox.leave`) and the services. `FakeTimedNotifier` and `FakeSlowCommunityNotifier` deleted, `FakeHeldNotifier`
    reduced, `FakeNotifier(refusing=...)` takes services.
  - **20**: the acceptance test covers the health alerter too (a fourth case); the `call_soon` callback is scheduled
    before the step's call, so it proves no suspension from the turn's start to `leave`; the spy records and the
    test's body asserts. `FakeRaisingNodeMetricStore` deleted with its exemption.
  - **23**: a third test of these limits, the wiring test, which the spec's "its two tests" did not count.
  - **25**: the read-back in the outbox's constructor; a failing read at the start stops it (an unreadable row no
    longer, from block 80); one warning per refused save; no `CHECK` on the table (nothing but its stores writes
    `local.db`); the JSON in ASCII; `absent_for` in microseconds; `Severity` by name.
  - **27**: `SAVES_FAILED` and `local_database_dependency()` live in `domain/observability/notification_sends.py`,
    beside `SENDS_FAILED`.
  - **28**: not in the approved spec; its row added by the lead.
  - **30**: 35 merged in; `RestartableBuilder[W]` generic in the works; `build_first` hands back the first works and no
    handle; the supervisor's record a class of `supervisor.py`; the contract `RestartableBuilderContract`; the fake
    split into `FakeRestartable` and `FakeRestartableBuilder`.
  - **37**: the block itself, cut out of 40; `supervise()` without works.
  - **40**: `SupervisedWork` without parts, the supervisor without the node's health; `BUGS` and the three-rebuild
    bound in `supervisor.py`; the rebuild's line `restarting client amuled: bugs in its works`; `notification_sending`
    takes the services; the debug lines `turns recorded on` and `rebuilt for bugs in` gone.
  - **45**: the works stop when the bugs turn failing, and the wait comes before the close and the build; the 60 s
    between two attempts of a rebuild that raised gives way to the series.
  - **50**: the supervisor's `not restarted again` line goes, the alert's line in its place; the lifecycle raised after
    the drain, so the close ran outside the bound, which block 80 fixed.
  - **53**: none.
  - **55**: `test_amule_client_works.py`'s shared channel part read from the node's health's log; `ExternalDependency`
    keeps `client_name` and `channel`, which `keyword_searches` reads.
  - **60**: the refused reading still raises its expected error, as on `main`: no status to publish, the supervisor's
    line at each turn kept.
  - **65**: the waits live in the adapter (amuleapi's limiter is its fact), on its monotonic clock. Only a `401` at the
    login arms them; a login answered without a token raises as before, unspaced. A session kept after a refused
    renewal sends its refused token once at the end of each wait. A client built anew, at a rebuild, starts its waits
    at 1 min again; the rebuild's own wait of 1 min at least, its works stopped, keeps two logins 60 s apart.
    `.claude/rules/amuleapi.md` gains the login limiter; `architecture.md` §10.1 the start and the waits.
  - **70**: each work's record keyed by its name in the log, so two works of one object with one name would share it
    (the keywords are deduplicated, and the test fakes take a name); a guard while a rebuild is under way, without
    which one rebuild counted in vain twice.
  - **72**: the unrepaired object and the restart in one block, the alerts in 74, so that no block keeps an
    unrepaired object with nothing ending the supervision. `RebuiltInVain` renamed `CrawlerFunctionLost`, carrying
    the function; the error reads `the crawl lost after 3 rebuilds`, the alert names each function's works. Its
    fix-back `3ef010c5`: a function is lost only once every one of its works is failing, a work that never turned not
    failing, as the lead reworded D34 to its approved rows.
  - **74**: a turn's verdict is a `Literal` (`enum` is not among the application ring's imports); the supervisor is
    built after the dispatcher, its close still pushed after the database connections.
  - **75**: each work `notification sending <service>` in the log; the shutdown's drain, `empty_the_outbox`, sends
    every service's entries at once and runs again while a send left another; the sender takes its own part from
    `service_dependencies`.
  - **80**: the close moves into `shutdown_bound`, which takes it; the lifecycle turns a cancelled drain of a restart
    into the restart's error (`raise restart from cut`); the unreadable row stated in the SQLite and outbox tests,
    not the contract (the fake cannot hold a row an earlier version wrote); no builder raises an expected error today,
    so the outage test raises `ClientUnreachableError`.
  - **82**: `NotifierRestartable.notifier`, `WebuiRestartable.thread` and `AmuleClientRestartable.client` kept: only
    the restartable builder contract reads them, to check that each object's works run over the state it was built
    with.
  - **90**: the spec's corrections (D26, section 5's sizes, section 6's rounds and two limits, the supervisor's record,
    block 25's read-back, appendix C's `open()`, appendix D).
- **Class 1**: block 20, `shield` removed from the core's asyncio names (`ast-grep/rules/core-import-names.yml`), with a
  refused case. None elsewhere.
- **Class 2 questions**: block 10, Serena's stale server (the operator reconnected it) and the line bound (block 5 cut
  out); 15, both bounds (accepted, 13 cut out); 20, the file bound (23 cut out); 25, both bounds (accepted, 27 cut
  out); 30, the cut (35 merged in, 28 cut out, "A"); 40, the size (37 cut out, accepted); 50, the draft's size (the
  operator's design instead); 55, the size (53 cut out, accepted); 80, the file bound (82 cut out). None in 13, 23,
  27, 28, 37, 45, 53, 60, 65, 70, 72, 74, 75, 82, 90.

## The holistic review's findings, and their exits

Over `git diff origin/main...origin/feat/login-tried-again` (2026-11-21): 0 CRITICAL, 2 MAJOR, 13 MINOR. The two MAJOR
settled with the operator as D32 to D34 before any code; every finding fixed in the lot, none to the backlog.

| Finding | Exit |
|---|---|
| MAJOR: a rebuild's count reset three turns after it, unless all three met a bug, so a healthy status reading kept it at 0 | fixed in 70 (D32): each work judged on its own turns, the count reset once every work that turned failing is healthy again; `test_supervisor_restarts.py::test_two_bugs_a_healthy_turn_then_three_bugs_after_a_rebuild_count_it_in_vain`, `::test_a_work_healthy_again_resets_no_count_while_another_is_still_failing` |
| MAJOR: a fast healthy work hid a bug at every turn of the slow ones (both eD2k searches cut, nothing rebuilt) | fixed in 70, 72 and 74 (D32 to D34): `test_supervisor.py::test_two_works_cut_at_every_turn_between_the_healthy_turns_of_two_others_rebuild_their_object`; a work three rebuilds do not repair leaves its object unrepaired, with its alert; the crawler restarts when a function is wholly lost |
| one work sent every service's entries, a service that never answers holding the others | fixed in 75: one work per service; `test_notifier_restartable.py::test_a_service_past_its_timeout_at_every_send_holds_none_of_another_service_s_entries` |
| an unreadable row stopped every start | fixed in 80: dropped in one warning line; `test_notification_outbox.py::test_an_entry_it_cannot_read_back_is_dropped_in_one_line`, `test_sqlite_notification_outbox_store.py::test_a_stored_notification_no_save_writes_is_read_back_unreadable_and_why` |
| the restart's close outside the shutdown bound, a deadline turning it into exit 0 | fixed in 80: the close within `shutdown_bound`, the restart's error kept; `test_crawler_composition_shutdown_bound.py`'s three restart tests, `test_crawler_lifecycle.py::test_a_deadline_cutting_the_drain_of_a_function_lost_keeps_its_error` |
| a wiring test unable to fail on a rule missing from `client_dependency` | fixed in 80: no `bug in` line asserted; `test_crawler_composition_wiring.py::test_a_reading_of_both_channels_connected_and_connectable_records_every_rule` |
| the notification sink read only after the stop | fixed in 80: `test_the_nodes_notifications_carry_its_id_in_their_username_and_title` waits for the node online before the SIGTERM |
| a rebuild's expected error counted in vain, its comment saying "no bug", its test staging a refused password | fixed in 80 as the finding's first option: counted in vain, as the lot 4b spec's D15 decided, the comment saying so; `test_supervisor_restarts.py::test_a_rebuild_meeting_amuled_unreachable_is_logged_in_one_line_and_counts_in_vain` |
| each change rewrote the whole table, a notification without a service included | fixed in 80 for an audience without a service (`test_notification_outbox.py::test_a_notification_for_no_service_is_neither_saved_nor_woken_for`); the n²/2 rows of a burst an accepted limit (above) |
| the tests written with no red step | fixed in 80: each run against a wrong stub, all failing (The tests watched failing) |
| `ExternalDependency.state()`, `HealthTransition.dependency` and `.rule` read by no source | fixed in 82: removed |
| the notifier's work recording through a `CheckRecorder` | fixed in 82: it takes `node_health: NodeHealth` |
| "a part of the node" for a dependency; the local database's saves missing from `domain/health/__init__.py` | fixed in 82: the docstrings, the package and §10.1 |
| one word for two things: "restart" for a rebuild, `restartable` for a name, `SupervisedObject` public | fixed in 72, 74 and 82: the ports say "rebuild"; `object_name` in `WorksStillFailing` and `WorksHealthyAgain`, `CrawlerRestartError` holding the function; `_SupervisedObject` |
| "(D24)" in a docstring | fixed in 82: dropped |

The review's conformance note on section 4's "What must not change" first row: run by this block (below).

## The tests watched failing

Each block's report lists every red step with its failure line, in its pull request body; one line per block here.

| Block | Red steps, against | Notes |
|---|---|---|
| 5 | a characterization test: one expected text deliberately wrong (`amuled reachable once more`), `At index 1 diff` | cannot fail first against code that exists |
| 10, 13, 28 | none: a rename, tests reading the notifications, a block adding no behaviour | |
| 15 | 26, against stubs returning `[]`, `""`, `()` or doing nothing | `test_a_send_cancelled_mid_send_keeps_its_entry` fell on a `TimeoutError` first, then failed on its assertion against a removal in a `finally`; the notifier restartable's contract works test fell on a `ValueError` (unpacking), re-watched on its assertion in 80 |
| 20 | the four no-suspension tests against the callers still on `dispatch_shielded` (`assert [True] == [False]`); the ast-grep case | |
| 23 | the two limits tests, against the limits still counting the notification | |
| 25 | 11, against stores and an outbox reading `()` and saving nothing | the row-shape test's first version fell on a `ValueError` (unpacking), rewritten to fail on its assertion |
| 27 | 9, against an unnamed part, empty plans, "saves failed" without an alert, `latest_save_failed` always `False`, a sender recording nothing | |
| 30 | 14, against builders handing back the same object, closes doing nothing, `build_first` returning `()` | |
| 37 | `supervise` running no object's work: `assert [] == [10.0, 20.0, 30.0]` | |
| 40 | 14 in `test_supervisor_restarts.py`, against `record_turn` returning `False` (or `met_a_bug`) | |
| 45 | 10, against `wait_before_rebuild` returning `timedelta(0)` | |
| 50 | 8, against an empty plan, an `except` returning 0, a give-up ending nothing, the lifecycle unchanged | |
| 53 | 3, against the disk's part still named `download tracking amuled` and the watcher recording only on a download tracking part | |
| 55 | 9, against transitions without their alert, `alert_event()` returning `None`, every rule mapped to `None`, a `NodeHealth` ignoring its dispatcher | the node's health reds first stopped on a `TypeError` (the stub still required `subscribers`), then failed on their assertions |
| 60 | 7, against the rule at 3 in a row, the alert mapped to `None`, empty plans, the watcher recording nothing, then recording "not detected" at every reading | |
| 65 | 7, below | |
| 70 | 4, against the parent's code judging the merged stream, such as `assert [0.0] == [0.0, 7380.0]` (both eD2k searches cut) | |
| 72 | 16, against every function `None`, #834's code, an empty loss check, an empty message, the lifecycle dispatching `WEBUI`; the fix-back's against the check before it | |
| 74 | 4, against empty messages and nothing dispatched | |
| 75 | 11 against an outbox and a sender ignoring their service, one work, a drain of one round; 1 against a drain of one round alone | |
| 80 | 10, against an unreadable entry filtered out silently, `UnreadableNotification(reason="")`, the code as it stood, a bound ignoring its close, `PASSWORD_REFUSED` missing, `notifier_works_over` handing back `()` | |
| 82 | none, no behaviour changed; the sender's tests, reworked over the node's health, each run against a wrong stub | |

Block 65's, each watched failing on its assertion:

| Test | Against | Failure |
|---|---|---|
| `test_crawler_composition_wiring.py::test_a_node_whose_password_amuled_refuses_runs_alerts_and_logs_in_once` (row "A refused password at the start") | `open()` catching the refusal in silence, no wait | `Left contains one more item: '/api/v1/auth/login'` |
| `test_amule_api_client_login_waits.py::test_a_call_after_a_refused_login_is_refused_at_once_without_asking` | the code as it stood | `Regex pattern did not match. Expected regex: 'the next login in 1 s' Actual message: 'amuleapi refused the admin password'` |
| `::test_open_tolerates_a_refused_password_in_one_warning` | `open()` catching the refusal in silence | `assert [] == ['login refus...): tolerated']` |
| `::test_each_refused_login_doubles_the_wait_before_the_next_30_min_at_most` | a wait of one minute at each refusal | `At index 2 diff: 2.0 != 3` |
| `::test_a_call_after_a_refused_renewal_is_refused_at_once_without_asking` | no check before a call on a kept session | `Expected regex: 'the next login in 60 s' Actual message: 'amuleapi refused the admin password: the next login in 120 s'` |
| `::test_calls_whose_token_is_refused_together_try_one_login` | the check in `_connect` alone, none under the renewal's lock | `Left contains one more item: '/api/v1/auth/login'` |
| `::test_a_login_accepted_brings_the_wait_after_the_next_refusal_back_to_1_min` | no reset at an accepted login | `assert [0.0, 1.0, 3.0, 4.0] == [0, 1, 3, 4, 5]` |

- **Every test the reports listed with no red step was run against a wrong stub** in blocks 80 and 82 (25 rows in
  #839's report, 6 in #840's), each failing; three on the raise they guard against rather than an assertion: the
  contract's `test_a_second_close_raises_nothing` (`RuntimeError: closed twice`),
  `test_a_refused_login_builds_a_client_all_the_same` (`ApiAuthError`) and `test_a_rule_without_an_alert_sends_nothing`
  (`AttributeError`: no stub returns an event without an alert). `test_no_service_has_nothing_to_send_and_so_no_sending`
  was deleted in 75, with no sender left without a service.
- **Written after the code, then watched failing on a wrong stub in 80**: block 25's `[of no kind]` and the wiring of
  the store, block 50's `test_crawler_restart_error.py`, block 53's two tests, block 72's text in the webui watch's
  restart test, block 74's expected notifications.
- **Tests moved or reshaped over unchanged behaviour, not re-watched**: listed in the reports of 15, 25, 27, 30, 37,
  40, 45, 75 and 82.

## Section 4's rows, where each is held

| Row | Test |
|---|---|
| A bug at every turn of the client's works | `test_supervisor_restarts.py::test_bugs_failing_rebuild_their_object_after_1_then_2_then_4_min_then_end_the_supervision` (the crawl lost at 904 s); its alert, `test_crawler_lifecycle.py::test_a_function_lost_has_its_alert_sent_local_db_refusing_then_raises_its_error` |
| A bug at every turn of one keyword's search, the others healthy | `test_supervisor_restarts.py::test_a_bug_at_every_turn_of_one_of_three_searches_rebuilds_their_object_3_times_then_no_more` |
| Both eD2k searches cut at their time limit, the status reading healthy | `test_supervisor.py::test_two_works_cut_at_every_turn_between_the_healthy_turns_of_two_others_rebuild_their_object` |
| Every search failing after the client's rebuilds, the status reading healthy | `test_supervisor_restarts.py::test_every_work_of_a_function_failing_after_three_rebuilds_ends_the_supervision_naming_it[the crawl]`; one search healthy, `::test_a_search_healthy_keeps_the_crawl_whatever_the_status_reading_meets` |
| Download and source tracking failing after the client's rebuilds | `::test_every_work_of_a_function_failing_after_three_rebuilds_ends_the_supervision_naming_it[the downloads]` |
| One of two services failing at every send, the other never sent to | `::test_one_of_two_services_failing_at_every_send_the_other_never_sent_to_leaves_it_unrepaired`; `::test_a_function_whose_other_work_never_turned_is_not_lost` |
| After three rebuilds in vain, the failing work healthy again | `::test_after_three_rebuilds_in_vain_its_work_healthy_again_has_the_next_bugs_rebuild_it` |
| The count's reset | `::test_two_bugs_a_healthy_turn_then_three_bugs_after_a_rebuild_count_it_in_vain` |
| Two in vain, ten healthy, then bugs | `::test_after_two_rebuilds_in_vain_ten_healthy_turns_then_bugs_rebuild_it_1_min_later` |
| The webui's thread dying | `test_webui_restartable.py::test_a_webui_whose_thread_ended_serves_again_once_rebuilt` |
| A bug at every send of the notifier | `test_supervisor_restarts.py::test_a_notifier_raising_a_bug_at_every_send_is_rebuilt_after_1_2_then_4_min_then_ends_it` |
| A bug in a Kad search | `test_keyword_search.py::test_a_bug_on_every_kad_search_logs_no_line_of_bugs_on_kad` |
| A refused password at the start | `test_crawler_composition_wiring.py::test_a_node_whose_password_amuled_refuses_runs_alerts_and_logs_in_once` (real time: one login while every work calls); the minute between logins on virtual time, `test_amule_api_client_login_waits.py::test_each_refused_login_doubles_the_wait_before_the_next_30_min_at_most` |
| A refused password while running | `test_status_watcher.py::test_a_refused_password_alerts_at_the_first_refused_reading_once`; the adapter's side, `test_amule_api_client_login_waits.py::test_a_call_after_a_refused_renewal_is_refused_at_once_without_asking` |
| The password right again | `test_status_watcher.py::test_a_refused_password_ends_at_the_first_answered_reading` |
| Connected to no network | `test_status_watcher.py::test_six_readings_on_no_network_fail_the_client_s_rule_and_nine_on_one_heal_it` |
| One service refusing | `test_notification_sender.py::test_a_service_refusing_every_send_fails_its_sends_in_the_log_and_alerts_no_one` |
| A notification decided, then stopped | `test_notification_outbox.py::test_a_notification_left_before_a_stop_is_sent_after_the_start`; through the node, `test_crawler_composition_wiring.py::test_a_notification_a_stop_left_unsent_is_sent_once_the_node_starts_again` |
| A decision's write and its notification | `test_nothing_is_awaited_between_...` in `test_file_judge.py`, `test_download_tracker.py`, `test_source_watcher.py` and `test_node_health.py` |
| `local.db` refusing every write | `test_notification_sender.py::test_a_local_database_refusing_every_save_still_sends_every_entry_and_its_alert` |
| The third rebuild in vain, `local.db` refusing | `test_crawler_lifecycle.py::test_a_function_lost_has_its_alert_sent_local_db_refusing_then_raises_its_error` |
| Two services, one refusing | `test_notification_sender.py::test_two_services_one_refusing_the_other_sent_once_the_refused_tried_once` |

No test runs a rebuild or a crawler restart through `CrawlerComposition`: no fault of the fakes drives the real
assembly to a bug, and a function lost takes 15 minutes of real time; the bound's own tests cover the restart's close.

## What must not change

| Check | Result |
|---|---|
| Today's alerts | `tests/application/test_health_alerts.py` (block 5), its cases and assertions unchanged to the lot's top, passing in the closing block's gate |
| aMule unreachable | nothing rebuilt, `test_status_watcher.py::test_amule_unreachable_fails_the_client_s_rule_and_rebuilds_nothing`; the alert, `::test_unreachable_alerts_at_two_minutes_and_ends_at_the_ninth_answer` |
| The matching decisions on the real catalog | **not run**: the umbrella's comparison reads the operator's `catalog.db`, outside the repository. The lot touches no matching code: `git diff --name-only origin/main...HEAD -- packages/crawler/src/p2pwatch/domain/matching packages/crawler/src/p2pwatch/adapters/driven/config` lists nothing (2026-11-21), and the gate's golden corpus passes |
| `deploy/matcher.yml` and its keys | `git diff --stat origin/main...HEAD -- deploy/` empty; `python -m p2pwatch validate-config` on `deploy/`'s three files, `AMULE_API_PASSWORD` set to a placeholder: `Config valid`, exit 0 (2026-11-21) |
| A healthy node's notifications, a channel's search cadence | at the release candidate |

## The lot's counts

- **Fix-backs: 1**, `3ef010c5` into block 72, its teammate's code following D34 as the lead worded it to its rows,
  before block 72 was first pushed.
- **Cascaded rebases: 1**, block 74 onto that fix-back, one conflict in `.claude/rules/glossary.md`: the first rebase
  aborted, block 74's teammate rebasing it and keeping both rows (the git reflog and #836's report, 2026-11-21).
- **Runs: 24 for the 24 pull requests #808 to #840**, one each, all green (`gh run list`, 2026-11-21); the closing
  block's starts at its push. **Runs re-triggered by a fix-back or a rebase: 0**, both coming before blocks 72 and 74
  were pushed.
- **Bodies the operator called unreadable**: none in the lead's brief to the closing block.
- **Stacking cost no more than pull requests in series**: 0 runs re-triggered for 25 blocks, no body called
  unreadable.
- **Re-cuts before any push**: 5 out of 10, 13 out of 15, 23 out of 20, 27 out of 25, 28 out of 30 and 35 merged into
  it, 37 out of 40, block 50's draft rewritten, 53 out of 55, 70 into 70, 72 and 74, 80 into 80 and 82.
- **`main` did not move during the lot**: its tip is the lot's base, `190cc145` (2026-11-18), at 2026-11-21.
- **The operator's choices**: the model in its review of lot 4b5's stack and the rename first (2026-11-18); blocks
  past a bound and the cuts above (2026-11-18 to 2026-11-21); block 50's design (2026-11-20); D32 to D34 in answer to
  the review's two MAJOR (2026-11-21); the stack past 19 blocks (2026-11-21). The lead's: D34 worded as its rows, the
  cuts within a bound, block 75 added for the review's MINOR, the exits of the review's other MINOR.

## For lot 7 (the operator pages)

The spec's appendix D, and the log lines that change:

- No `<part>, bugs: ...` line. A rebuild: `restarting client amuled: bugs in its works`, then `restarting client amuled
  again, 1 of 3 rebuilds in vain: bugs in its works`, `client amuled rebuilt`, `rebuild of client amuled: <error>` (a
  rebuild that met an expected error, counted in vain), `bug in the rebuild of client amuled` (with its trace); the
  same for `webui` and `notifier`.
- The third rebuild in vain: the operations alert `client amuled: search 'keroro' amuled ed2k still failing after 3
  rebuilds: a bug of its own, or a shared state a crawler restart would renew` (two works: `of their own`), its end
  `client amuled: every work healthy again`; `notifier: notification sending discord operations still failing ...` for
  a service.
- A function wholly lost: the operations alert `the crawl lost: every search failing after 3 rebuilds: the crawler
  restarts` (`the webui lost: its thread watch failing ...`, `the notifications lost: every notification sending
  failing ...`, `the downloads lost: every download and source tracking failing ...`), then `Workers stopped.`,
  `amuled session closing…`, `Databases closed: exiting.`, then `Exiting for a restart: the crawl lost after 3
  rebuilds` on stderr, exit code 1, Docker starting the crawler again. A node failing without end restarts about every
  15 minutes for works turning every minute, one alert each round.
- The notifier: one work per service, `notification sending discord community`; `bug in notification sending discord
  community` (error, with its trace); a refusal or a timeout keeps its line, under
  `p2pwatch.application.steps.notification_sender`. Each service is sent to by its own work, so a service that never
  answers holds no other.
- The outbox at the start: `<n> notification(s) dropped, unreadable: <reasons>` and `<n> notification(s) dropped,
  their service no longer configured: discord community 2`; then `notification outbox not saved (<error>): saved again
  at its next change`; `local database, saves failed: ...`, the alert `notifications not saved in local.db: lost at the
  next restart`, its end `notifications saved again`. A notification may be sent twice after a restart; one refused by
  its service is not sent again.
- `download disk, disk space low: ...` and `client amuled, connected to no network: ...` replace the `download
  tracking amuled, ...` lines; the latter on a crawl-only node too.
- A refused password: `login refused at startup (amuleapi refused the admin password: the next login in 60 s):
  tolerated`, then at each turn of each work over the client `<work>: amuleapi refused the admin password: the next
  login in <n> s`; `client amuled, password refused: unknown to failing` and the alert `amuled refuses the password:
  check the configuration`, its end `amuled accepts the password again`. It no longer stops the node at its start; a
  corrected password is taken at the next login, 30 min later at most.
- The time limits at debug level: `status reading amuled`, `download tracking amuled` and `source tracking amuled` 1020
  s (they no longer count a notification timeout); each `notification sending <service>` one send's timeout plus 300 s.

## Pitfalls learned

- **A long-running Serena server goes stale across branch switches, silently**: its first rename wrote edits at
  shifted offsets (blocks 10, 53); the operator reconnected it, after which every rename reached every reference
  (block 10). Check each rename's diff, never its "changes applied" count, then `git grep -w`. Serena never reaches a
  dataclass's keyword arguments, a string annotation, a parameter or an instance attribute: mypy's errors list them
  (blocks 10, 23). Its view of files edited outside it goes stale too (block 20).
- **A branch renamed under `gh stack` loses its tracking**: `refactor/works-judged-alone`, renamed
  `feat/works-judged-alone` with `git branch -m` (2026-11-21). A block's branch takes its spec row's name before
  `gh stack add`.
- **A stub restored within the same second leaves its `.pyc` in use** when it has the size of the code it replaces:
  the next run still runs the stub (block 80). Run each red check with `PYTHONDONTWRITEBYTECODE=1`.
- **A conversation branch cut off left messages to teammates under the lead's name, and a spec edit uncommitted in the
  tree** (2026-11-21): a teammate stops and asks the lead on a message that contradicts its brief, even under the
  lead's name, and a block starts from a clean tree.
- **`tach` forbids the composition a driven port**: the sender's builder takes an `AppriseNotifier` (block 15).
- **`FakeTime`'s sleeps end at once**, so every turn's time limit expires at its first suspension (block 15).
- **`git grep` misses untracked files**: a fake looked unused while only a new test read it (block 15).
- **`sqlite3.Connection` as a context manager commits but never closes**: use `closing(...)` (block 25). A refused
  `FULL` write needs a write larger than the pages left (block 25). A fake's test module goes in
  `tests_without_unit` (block 25).
- **The local database's save is recorded before a send's bug is raised**, or a bug at every send would leave the rule
  unrecorded (block 27).
- **A `Mapping` is invariant in its key** (block 30). A fake builder handing back the same work instances makes a
  rebuilt object's works take their first turn at once (blocks 40, 45). A test work whose wait returns at once spins
  once every object's works run (block 37). Three works waking at one instant give three turns in a row (block 40).
- **mypy types `2**n` as `Any`**: the doubling is `1 << n` (block 45).
- **`asyncio.Event` is not among the core's asyncio names**: the restart travels through an `asyncio.Queue`; waiting
  on the run state through a task adds loop turns, hence the check before each turn; on virtual time, a run that
  never ends trips the loop's deadlock assertion (block 50).
- **The dispatcher is built before the node's health**; the closures building the notifier's works read the node's
  health when called. Ruff's `PLR0917` refuses a second positional parameter in a test helper (block 55).
- **"Not detected" on the password only under an answered status**: recorded at every reading that did not raise, an
  unreachable reading would end the alert and the next refusal send it again (block 60).
- **The login's wait is checked in two places** (block 65): under the login lock, in `_login`, for calls whose token
  was refused together; and before each call, in `_call`, for a session kept after a refused renewal, which would
  send its refused token at each call (amuleapi's token limiter, 30 in 60 s). A test of the reset written before both
  passed for the wrong reason: every renewal logged in.
- **A locked-out login answers `429 rate_limited`**, which the adapter maps to unreachable, never to a refused
  password (aMule's `docs/api/REFERENCE.md`, "Rate limiting"; block 65).
- **A work's record is keyed by its name in the log**: two works of one object named alike would share it (block 70).
- **The unrepaired alert and its end are dispatched outside a turn**, in a work's task or the rebuild's: a bug planning
  them escapes the supervision, so the policy's rows cover both plans (block 74).
- **A stub sender ignoring its service still sends every service's entries**, so the drain's rounds could go red only
  once the sender filtered by its service; every sender waits on the one `WakeSubject.NOTIFICATION`, each wake waking
  them all (block 75).
- **Python 3.13's `asyncio.timeout` lets an exception other than a cancellation leave an expired timeout as it is**,
  which is how the restart's error passes the bound (block 80). A SIGTERM before any search was read cut a request
  mid-body, and the fake amuleapi server raised `JSONDecodeError` at its exit: the test waits for a search first.
- **The node's health's log shows only a change of state**: a sender's test over it takes three turns to turn a rule
  (block 82).

## Not validated

- Nothing ran against a real node: no rebuild through `CrawlerComposition`, no object left unrepaired, no function lost,
  no exit code under Docker's restart policy, no real full disk or broken `local.db`, no row left by an earlier
  version, no real Discord or ntfy send nor a service that never answers, no entry left in the outbox across a real
  restart (the spec's release candidate check), no refused password against a real amuled at the start, while running
  or at a rebuild (the release candidate check of "A refused password at the start"), no 30 min cap on a real clock.
- **Integration suites**, against `p2pwatch-amule:dev` (built 2026-11-16, nothing under `packages/amule` changed
  since), a fresh daemon, `-p 14711:4711`, `P2PWATCH_TEST_API_HOST=127.0.0.1 P2PWATCH_TEST_API_PORT=14711
  P2PWATCH_TEST_API_PASSWORD=indexer-api-test`, at `32fb27e3` (the closing block's parent, whose code it leaves
  unchanged), 2026-11-21: `api_integration`, `download_integration` and `orchestration_integration` together, `6
  passed, 3124 deselected in 22.82s`, among them `test_real_login_fails_with_wrong_password` (a real amuled's refusal
  read as `ApiAuthError`) and `test_real_loop_runs_one_search_and_stops` (`CrawlerComposition` over a real amuled, one
  search, then a stop within its bound). `compose_integration` did not run: the lot changes no image, no compose file,
  and of aMule's adapters only the client's login, which the daemon suites cover.
- The matching comparison on the real catalog (What must not change).

## `BACKLOG.md`

Reconciled: the sub-entry "Lot 4b6, the health model redrawn" of "v5 release readiness" deleted, the lot shipping with
this stack; the sub-entry "Lot 4c" corrected as the spec's section 6 says: the graph of dependencies, what the Node page
and `/health` show of an unrepaired object, the real stops as D34's functions lost, its draft's D17 superseded. The lot
adds nothing.

## Next step

The operator reads and merges the stack, rebased onto `main` if it moved. No release: v5 ships after lots 4c to 7 and
their release candidates.

Then lot 4c, what the operator sees of health: its spec, drafted in `agents/specs/2026-11-09-v5-fault-isolation.md`,
rewritten on this lot's names (`ExternalDependency`, `HealthAlert`, `NodeHealth`, `NotificationOutbox`,
`_SupervisedObject`, `RestartableBuilder`, `CrawlerFunction`, `outage`, `unrepaired`), its own Discuss and Spec first.
Its D17 is superseded by D34; its Node page and `/health` show an unrepaired object; its alerts on the notification
services' rules must not go through the notifier.

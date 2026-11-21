# Handoff: v5 lot 4b6, the health model redrawn (tier Spec)

Drafted by block 65's teammate from the block reports (#808 to #832, the collapsed "Block report" of each pull request
body) and its own. To be corrected by the closing block, which also fixes the holistic review's findings. Spec:
`agents/specs/2026-11-18-v5-lot-4b6-health-model-redrawn.md`, decisions D20 to D31, which replace the lot 4b spec's
D1, D4, D6 and D14 to D16. Once this stack has merged, lot 4c's spec is rewritten on this lot's names.

## Current state

- **Two causes, two answers** (D20, D21). A bug is our code's: anything a turn raises but an `ExpectedError`. The
  supervisor counts it on the object it can rebuild. An outage is outside the program: a rule of an external
  dependency failing, which the node's health logs and alerts on. No log line says a part has bugs.
- **`ExternalDependency`** (`domain/health/external_dependency.py`, `Component` renamed) is what can have an outage:
  `client amuled` (unreachable, connected to no network, password refused), `channel amuled ed2k` and `channel amuled
  kad` (not connected, not connectable, searches failed), `download disk` (disk space low, on a node that downloads),
  `local database` (saves failed) and each `notifier <service>` (sends failed). Its `rules` map each rule to its
  `HealthAlert` or `None`; a `HealthTransition` carries its rule's alert, and `alert_event()` gives the alert, its end,
  or nothing for a rule healthy from its first checks. Each builder (`client_dependency`, `channel_dependency`,
  `download_disk_dependency`, `local_database_dependency`, `notification_service_dependencies`) builds its alerts from
  the node's id and, for the disk, its floor. No alert names a service's rule: it would go through that service.
- **`NodeHealth`** (`application/steps/node_health.py`) tracks the outages alone: `record(on=..., rule=...,
  detected=...)` logs each change and dispatches its rule's alert, nothing awaited before the entry is left. The
  health alerter, its `_RULES_WITHOUT_AN_ALERT` and `HealthSubscriberBuiltLater` are gone: the dispatcher is built
  first, since it needs only the outbox.
- **Every notification goes through `NotificationOutbox`** (`application/steps/notification_outbox.py`): the
  dispatcher plans, logs, writes the metrics, then `leave`s one `PendingNotification` per service of its audience,
  without awaiting anything, and wakes `WakeSubject.NOTIFICATION`. The notifier's work, `NotificationSender`
  (`notification sending` in the log), sends the oldest entry within `notification_timeout_seconds`, records "sends
  failed" on its service and "saves failed" on the local database, and removes the entry once its send has ended
  (sent, refused, past its timeout, or met a bug, a bug of its turn); a cancelled send keeps its entry. One work over
  every service: a bug of a send is the notifier's. At the shutdown, the lifecycle sends what is left through a
  notifier it built at the start, within the shutdown bound. `dispatch_shielded`, `finish_shielded_dispatches`,
  `CurrentNotifier` and the notification timeout in `AmuleWorkTimeLimits` are gone.
- **The outbox is saved in `local.db`** at each change (`NotificationOutboxWriter.set_pending_notifications`,
  `NotificationOutboxReader.read_pending_notifications`, one adapter, `SqliteNotificationOutboxStore`, table
  `pending_notifications`, migration `local/0017`), the four kinds of notification in a JSON object under `kind`. It
  reads itself back in its constructor, drops the entries of a service no longer configured in one log line, and
  still sends from memory: a refused save is one warning, and the outbox keeps whether its latest save failed, which
  the notifier's work records at each turn.
- **Each object the node can rebuild is built whole** (`Restartable`: `works()`, `close()`; `RestartableBuilder`:
  `build()`, the first included): the aMule client (`composition/amule_client_restartable.py`), the webui
  (`webui_restartable.py`), the notifier (`notifier_restartable.py`). The client's channels (`CHANNELS`) and the
  request bound are known before any client is built.
- **The supervisor alone decides each rebuild and runs it** (`application/steps/supervisor.py`). `build_first` builds
  each object and keeps it in a `SupervisedObject`; `supervise()` runs the works of the objects it built, and only
  those. Each turn is recorded on its object by `BUGS`' thresholds (failing at 3 in a row, healthy again under 2 in
  the last 10), forgotten at each rebuild. Once they turn failing, the object's works stop, then after 1, 2, then 4
  minutes (in memory, on the monotonic clock) it is closed, rebuilt, and its new works run. A rebuild is in vain when
  the bugs turn failing again before they are healthy, or when it raises; the count resets once they are healthy. The
  restart policy, its request and runner, `node_restart_policy`, the bugs rule of every dependency and the four parts
  that held it alone are gone.
- **The third rebuild in vain ends the supervision** with a `CrawlerRestartError`: the lifecycle dispatches the alert
  `client amuled rebuilt 3 times in vain: the crawler restarts`, empties the outbox and raises; the command line
  prints `Exiting for a restart: ...` and exits 1, and `restart: unless-stopped` has Docker start the crawler again,
  `amuled` untouched. Each work checks the run state before each turn.
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

- **A node whose cause survives its own restart restarts every 7 minutes and its start, without end**, an alert at
  each round (the operator, 2026-11-18).
- **A notification can be sent twice** when the node stops between its send and the save of its removal.
- **A notification is lost when the process is killed** between a decision's write and the save of its entry, or
  before its save when `local.db` cannot be written.
- **A notification refused by its service, or whose send met a bug, is lost.**
- **A kept entry goes to the service that bears its name at the start**: two URLs of one scheme and audience swapped
  between two runs swap their entries.
- **When the notifier's bug survives the restart, its alerts never go out**; the log keeps them.
- **A rule that no code records stays unknown, and nothing says so.**

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
| 65 | | `feat/login-tried-again` | the login tried again after waits that double, a refused password tolerated at the start | 247, 9 |
| 80 | | `fix/lot-4b6-review-fixes` | the holistic review's fixes | |
| 90 | | `docs/lot-4b6-wrap` | closing block | |

- **Past a bound, accepted by the operator**: 10 on its row of the spec (a rename); 15 at 1 542 lines and 31 files,
  block 13 cut out first (2026-11-18); 25 at 913 lines and 22 files, block 27 cut out (2026-11-19); 30 at 1 034
  lines and 29 files, block 35 merged in, block 28 cut out ("A", 2026-11-20); 40 at 1 846 lines and 40 files, about
  1 100 removed, block 37 cut out (2026-11-20); 55 at 1 012 lines and 30 files, 683 removed, block 53 cut out
  (2026-11-21).
- **Cut by the lead within a bound**: 5 out of 10 (663 lines with the test); 23 out of 20 at the commit boundary (25
  files together).
- **Block 50's first draft** (the run state carrying the error, the supervisor requesting the shutdown) measured 416
  lines and 24 files; the operator chose that the supervisor ends its own supervision and the lifecycle dispatches the
  alert (spec corrected in `c7f9d6c9`); the draft's commits were dropped and rewritten.
- **Departures, per block**:
  - **5**: the test is `tests/application/test_health_alerts.py`, testing no single module, hence its
    `tests_without_unit` entry. Later blocks change only its setup (`_status_alerts`, `_disk_alerts`): 55 builds it
    without the alerter, every case and assertion unchanged.
  - **10**: every log text kept (`client amuled, unreachable: ...`); the four parts holding the bugs rule alone carry
    the new name until block 40. The ast-grep rule over the record is `external-dependency-record-through-node-health`.
  - **15**: one work over every service, so a send's bug is recorded on every service's bugs rule, D25 a block early;
    the bug's line is the supervisor's `bug in notification sending`; the shutdown's last sends go through a notifier
    the lifecycle builds at the start; the outbox waits through the `Waker` port; no service configured, no work. The
    dispatcher takes a `leave_notification` callback (`outbox.leave`) and the services. `FakeTimedNotifier` and
    `FakeSlowCommunityNotifier` deleted, `FakeHeldNotifier` reduced, `FakeNotifier(refusing=...)` takes services.
  - **20**: the acceptance test covers the health alerter too (a fourth case); the `call_soon` callback is scheduled
    before the step's call, so it proves no suspension from the turn's start to `leave`; the spy records and the
    test's body asserts. `FakeRaisingNodeMetricStore` deleted with its exemption.
  - **23**: a third test of these limits, the wiring test, which the spec's "its two tests" did not count.
  - **25**: the read-back in the outbox's constructor; a failing read at the start stops it; one warning per refused
    save; no `CHECK` on the table (nothing but its stores writes `local.db`); the JSON in ASCII; `absent_for` in
    microseconds; `Severity` by name.
  - **27**: `SAVES_FAILED` and `local_database_dependency()` live in `domain/observability/notification_sends.py`,
    beside `SENDS_FAILED`.
  - **28**: not in the approved spec; its row added by the lead.
  - **30**: 35 merged in; `RestartableBuilder[W]` generic in the works; `build_first` hands back the first works and no
    handle; `SupervisedObject` a class of `supervisor.py`; the contract `RestartableBuilderContract`; the fake split
    into `FakeRestartable` and `FakeRestartableBuilder`.
  - **37**: the block itself, cut out of 40; `supervise()` without works.
  - **40**: `SupervisedWork` without parts, the supervisor without the node's health; `BUGS` and the three-rebuild
    bound in `supervisor.py`; the rebuild's line `restarting client amuled: bugs in its works`; `notification_sending`
    takes the services; the debug lines `turns recorded on` and `rebuilt for bugs in` gone.
  - **45**: the works stop when the bugs turn failing, and the wait comes before the close and the build; the 60 s
    between two attempts of a rebuild that raised gives way to the series.
  - **50**: the supervisor's `not restarted again` line goes, the alert's line in its place; the lifecycle raises after
    the drain, so the composition's bounded `stack.aclose()` is skipped and the resource stack's own close at exit
    (5 s) closes everything; `Workers stopped.` is not printed.
  - **53**: none.
  - **55**: `test_amule_client_works.py`'s shared channel part read from the node's health's log; `ExternalDependency`
    keeps `client_name` and `channel`, which `keyword_searches` reads.
  - **60**: the refused reading still raises its expected error, as on `main`: no status to publish, the supervisor's
    line at each turn kept.
  - **65**: the waits live in the adapter (amuleapi's limiter is its fact), on its monotonic clock. Only a `401` at the
    login arms them; a login answered without a token raises as before, unspaced. A session kept after a refused
    renewal sends its refused token once at the end of each wait. A client built anew, at a rebuild, starts its waits
    at 1 min again; the rebuild's own wait of 1 min at least, its works stopped, keeps two logins 60 s apart. The
    supervisor's comment on a rebuild's expected error, which named a refused password, is generic now; the
    composition's comment on the node's id resolved before the login goes. `.claude/rules/amuleapi.md` gains the login
    limiter; `architecture.md` §10.1 the start and the waits.
- **Class 1**: block 20, `shield` removed from the core's asyncio names (`ast-grep/rules/core-import-names.yml`), with a
  refused case. None elsewhere.
- **Class 2 questions**: block 10, Serena's stale server (the operator reconnected it) and the line bound (block 5 cut
  out); 15, both bounds (accepted, 13 cut out); 20, the file bound (23 cut out); 25, both bounds (accepted, 27 cut
  out); 30, the cut (35 merged in, 28 cut out, "A"); 40, the size (37 cut out, accepted); 50, the draft's size (the
  operator's design instead); 55, the size (53 cut out, accepted). None in 13, 23, 27, 28, 37, 45, 53, 60, 65.

## The holistic review's findings, and their exits

Not run yet: the lead dispatches it once this block's pull request is open, over `git diff
origin/main...origin/feat/login-tried-again`. The closing block fills this section.

## The tests watched failing

Each block's report lists every red step with its failure line, in its pull request body; one line per block here.

| Block | Red steps, against | Notes |
|---|---|---|
| 5 | a characterization test: one expected text deliberately wrong (`amuled reachable once more`), `At index 1 diff` | cannot fail first against code that exists |
| 10, 13, 28 | none: a rename, tests reading the notifications, a block adding no behaviour | |
| 15 | 26, against stubs returning `[]`, `""`, `()` or doing nothing | `test_a_send_cancelled_mid_send_keeps_its_entry` fell on a `TimeoutError` first, then failed on its assertion against a removal in a `finally`; the notifier restartable's contract works test fell on a `ValueError` (unpacking), not an assertion |
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

- **No red step, by design or as reported**: block 15's `test_a_turn_with_nothing_left_sends_and_records_nothing`,
  `test_no_service_has_nothing_to_send_and_so_no_sending`, and `test_a_service_refusing_every_send_fails_its_sends_in_the_log_and_alerts_no_one`
  (written against the finished sender); block 20's and 23's wiring test of the time limits (failed after the change
  on its old values, then corrected); block 25's contract `test_no_entry_is_read_before_the_first_save` and
  `test_a_save_of_no_entry_leaves_none`, SQLite's `[of no kind]` and the wiring test (written after the composition);
  block 30's `test_a_second_close_raises_nothing`, the contract's works test for the three real builders and
  `test_a_client_built_anew_spaces_its_first_ed2k_search_from_the_one_built_before`; block 40's
  `test_a_bug_on_every_kad_search_logs_no_line_of_bugs_on_kad` (nothing can log a part's bugs once the supervisor
  holds no node's health); block 45's `test_each_rebuild_names_its_object_and_how_many_came_before_in_vain`; block
  50's `test_crawler_restart_error.py` (written after the error) and the run state's check before each turn (three
  existing tests failed without it); block 53's `test_the_download_disk_is_named_after_it_and_by_no_client` and
  `test_the_status_reading_records_no_network_on_the_client_s_part_downloading_or_not` (written after the code);
  block 55's eight guards; block 65's `test_amule_client_restartable.py::test_a_refused_login_builds_a_client_all_the_same`
  (rewritten from `test_a_refused_login_raises_and_the_next_build_logs_a_client_in`; its behaviour is `open()`'s).
- **Tests moved or reshaped over unchanged behaviour, not re-watched**: listed in the reports of 15, 25, 27, 30, 37,
  40 and 45.

## Section 4's rows, where each is held

| Row | Test |
|---|---|
| A bug at every turn of the client's works | `test_supervisor_restarts.py::test_bugs_failing_rebuild_their_object_after_1_then_2_then_4_min_then_end_the_supervision`; its alert, `test_crawler_lifecycle.py::test_the_third_rebuild_in_vain_has_its_alert_sent_local_db_refusing_then_raises_its_error` |
| One keyword's search | `test_supervisor_restarts.py::test_a_bug_at_every_turn_of_one_of_three_works_rebuilds_nothing_each_logged_with_its_trace` |
| Two in vain, ten healthy, then bugs | `test_supervisor_restarts.py::test_after_two_rebuilds_in_vain_ten_healthy_turns_then_bugs_rebuild_it_1_min_later` |
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
| The third rebuild in vain, `local.db` refusing | `test_crawler_lifecycle.py::test_the_third_rebuild_in_vain_has_its_alert_sent_local_db_refusing_then_raises_its_error` |
| Two services, one refusing | `test_notification_sender.py::test_two_services_one_refusing_the_other_sent_once_the_refused_tried_once` |

No test runs a rebuild or a crawler restart through `CrawlerComposition`: no fault of the fakes drives the real
assembly to a bug, and the third rebuild in vain takes 7 minutes of real time.

## What must not change

| Check | Result |
|---|---|
| Today's alerts | `tests/application/test_health_alerts.py` (block 5), its cases and assertions unchanged to the lot's top, passing at `d55455a9` |
| aMule unreachable | nothing rebuilt (an `ExpectedError` is no bug); the alert, `test_status_watcher.py::test_unreachable_alerts_at_two_minutes_and_ends_at_the_ninth_answer` |
| The lot 4b spec's table (the matching decisions on the real catalog, `deploy/matcher.yml`, a healthy node's notifications and search cadence) | for the closing block: not run by any block |

## The lot's counts

- Fix-backs: 0. Cascaded rebases: 0 (to block 65).
- Runs: 17 for the 17 pull requests #808 to #832, one each, all green (`gh run list`, 2026-11-21); block 65's
  started at its push. Runs re-triggered by a fix-back or a rebase: 0.
- Bodies the operator called unreadable: for the closing block.
- The operator's choices: blocks past a bound and the cuts above (2026-11-18 to 2026-11-21); block 50's design
  (2026-11-20).

## For lot 7 (the operator pages)

The spec's appendix D, and the log lines that change:

- No `<part>, bugs: ...` line. A rebuild: `restarting client amuled: bugs in its works`, then `restarting client amuled
  again, 1 of 3 rebuilds in vain: bugs in its works`, `client amuled rebuilt`, `rebuild of client amuled: <error>` (a
  rebuild that met an expected error), `bug in the rebuild of client amuled` (with its trace); the same for `webui`
  and `notifier`.
- The third rebuild in vain: the operations alert `client amuled rebuilt 3 times in vain: the crawler restarts`, then
  `Exiting for a restart: ...` on stderr, exit code 1, Docker starting the crawler again. A node failing without end
  restarts every 7 minutes and its start, one alert each round.
- The notifier: `bug in notification sending` (error, with its trace); a refusal or a timeout keeps its line, under
  `p2pwatch.application.steps.notification_sender`. The services of an audience are sent to one after the other,
  oldest first.
- The outbox: `<n> notification(s) dropped, their service no longer configured: discord community 2` at the start;
  `notification outbox not saved (<error>): saved again at its next change`; `local database, saves failed: ...`, the
  alert `notifications not saved in local.db: lost at the next restart`, its end `notifications saved again`. A
  notification may be sent twice after a restart; one refused by its service is not sent again.
- `download disk, disk space low: ...` and `client amuled, connected to no network: ...` replace the `download
  tracking amuled, ...` lines; the latter on a crawl-only node too.
- A refused password: `login refused at startup (amuleapi refused the admin password: the next login in 60 s):
  tolerated`, then at each turn of each work over the client `<work>: amuleapi refused the admin password: the next
  login in <n> s`; `client amuled, password refused: unknown to failing` and the alert `amuled refuses the password:
  check the configuration`, its end `amuled accepts the password again`. It no longer stops the node at its start; a
  corrected password is taken at the next login, 30 min later at most.
- The time limits at debug level: `status reading amuled`, `download tracking amuled` and `source tracking amuled` 1020
  s (they no longer count a notification timeout).

## Pitfalls learned

- **A long-running Serena server goes stale across branch switches, silently**: its first rename wrote edits at
  shifted offsets (blocks 10, 53). Check each rename's diff, never its "changes applied" count, then `git grep -w`.
  Serena never reaches a dataclass's keyword arguments, a string annotation, a parameter or an instance attribute:
  mypy's errors list them (blocks 10, 23). Its view of files edited outside it goes stale too (block 20).
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
- **The dispatcher is built before the node's health**; the closures building the notifier's work read the node's
  health when called. Ruff's `PLR0917` refuses a second positional parameter in a test helper (block 55).
- **"Not detected" on the password only under an answered status**: recorded at every reading that did not raise, an
  unreachable reading would end the alert and the next refusal send it again (block 60).
- **The login's wait is checked in two places** (block 65): under the login lock, in `_login`, for calls whose token
  was refused together (each would see the login count unchanged and log in); and before each call, in `_call`, for
  a session kept after a refused renewal, which would send its refused token at each call (amuleapi's token limiter,
  30 in 60 s). A test of the reset written before both passed for the wrong reason: every renewal logged in.
- **A locked-out login answers `429 rate_limited`**, which the adapter maps to unreachable, never to a refused
  password (aMule's `docs/api/REFERENCE.md`, "Rate limiting"; block 65).

## Not validated

- Nothing ran against a real node: no rebuild through `CrawlerComposition`, no third rebuild in vain, no exit code under
  Docker's restart policy, no real full disk or broken `local.db`, no real Discord or ntfy send, no entry left in the
  outbox across a real restart (the spec's release candidate check), no refused password against a real amuled at the
  start, while running or at a rebuild (the release candidate check of "A refused password at the start").
- **Integration suites**: no block ran them. Block 65 changed the amuleapi adapter: `api_integration` is worth one run
  against `p2pwatch-amule:dev` on port 14711 before the merge.
- The lot 4b spec's "What must not change" table (above).

## `BACKLOG.md`

For the closing block: the sub-entry "Lot 4b6, the health model redrawn" of "v5 release readiness" goes once this
stack merges; the sub-entry "Lot 4c" names its draft's rewrite on this lot's names (the spec's section 6: D17
superseded by D27, the graph of parts becoming the graph of dependencies).

## Next step

The holistic review over the stack, then the closing block (its findings fixed, this handoff and the spec's
corrections, `BACKLOG.md`). The operator reads and merges the stack, rebased onto `main` if it moved. No release: v5
ships after lots 4c to 7 and their release candidates.

Then lot 4c, what the operator sees of health: its spec, drafted in `agents/specs/2026-11-09-v5-fault-isolation.md`,
rewritten on this lot's names (`ExternalDependency`, `HealthAlert`, `NodeHealth`, `NotificationOutbox`,
`SupervisedObject`, `RestartableBuilder`, `outage`), its own Discuss and Spec first. Its D17 is superseded by D27, and
its alerts on the notification services' rules must not go through the notifier.

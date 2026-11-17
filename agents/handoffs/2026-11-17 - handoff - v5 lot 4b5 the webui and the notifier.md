# Handoff: v5 lot 4b5, the webui and the notifier (tier Spec)

Drafted by block 53's teammate from the block reports (#791, #792, the collapsed "Block report" of each pull
request body) and its own, for the closing block to correct. Spec: `agents/specs/2026-11-15-v5-lot-4b-health-model.md`,
lot 4b5 of its five lots (D19), decisions D14, D15, D17, D18. The last lot of lot 4b: once it has merged, the health
model and the restarts are whole.

## Current state

- **The webui is a part of the node** (`webui`, `webui_component` in `domain/work_components.py`), judged on its bugs
  alone. `WebuiThreadWatch` (`application/steps/webui_thread_watch.py`) is a work that looks every minute, the first
  look included, whether the webui's thread still runs, through `UvicornServerThread.is_alive`, which the composition
  passes as a callback; a thread that has ended raises `WebuiThreadEndedError`, a bug. Its time limit is the 5 minutes
  of margin alone. `Component.client_name` may be `None` now; the alerter refuses a client's alert for such a part.
- **`WebuiRestartable`** (`composition/webui_restartable.py`) stops the old thread, serves the webui on a thread built
  anew (a new app and new read connections) and hands back the watch over it (`webui_thread_watch_over`). A port held
  elsewhere does not make the rebuild raise: the new thread ends, its watch finds it ended, and after three rebuilds in
  vain the webui is not restarted again.
- **`node_restart_policy`** (`composition/node_restart_policy.py`, which replaces `amule_client_restart_policy`)
  maps each object to the parts its first works are recorded on, and takes `parts_without_works` (required) for the
  parts no work is recorded on: the notification services' parts, which the dispatcher records each send on.
- **Each notification URL is a service** (`NotificationService`, `domain/observability/notification_sends.py`), named
  by its URL's scheme and its audience, never by its URL, which carries a webhook's token: `discord community`, a
  second alike `discord community 2`, a URL without `://` of the scheme `unknown`. The `Notifier` port lists its
  services (`services()`, equal from a notifier built anew on the same configuration) and sends to one
  (`notify(service, notification=...)`).
- **`AppriseNotifier`** sends to one service through an apprise object holding that URL alone, built per node at its
  first notification there (the asset names the node); the node prefix goes in the titles of the services that ask for
  it. Any answer but a success raises `NotificationRefusedError` (an `ExpectedError`): `the service refused it
  (FAILURE)`, and `apprise could not load its URL` for a URL apprise cannot load, at each send.
- **The dispatcher** (`ObservabilityDispatcher`) sends a notification to every service of its audience together (a
  `TaskGroup`), so it takes one `notification_timeout_seconds` at most, as the time limits count it; once every send
  has ended, it records each on its service's part (`notifier discord community`): a send that worked, not detected
  on "bugs" and on "sends failed"; a refusal or a send past the timeout, detected on "sends failed", not on "bugs"; any
  other exception, detected on "bugs", nothing on "sends failed". A `TimeoutError` the notifier raises itself is a bug.
  The dispatcher reaches the notifier through `CurrentNotifier`, at each notification, so a send in flight during a
  rebuild finishes on the old one.
- **`NotifierRestartable`** (`composition/notifier_restartable.py`) holds the apprise notifier built latest; a rebuild
  builds it anew and hands back no work. The composition builds the services' parts once, on the first notifier's
  services, and gives them all to the policy as the notifier's.
- **`NotifierContract`** (`tests/contracts/application/ports/driven/notifier_contract.py`): two notifiers built on one
  configuration list the same services, a send its service takes raises nothing, a refused one
  `NotificationRefusedError`. `AppriseNotifier` and `FakeNotifier` run it; five other doubles are exempted, each with
  its reason.
- **No alert names the webui's or the services' rules**: an alert about the notifier would go through the notifier.
  Their changes are log lines.

## Accepted limits

The spec's section 6, those this lot reaches, and one the operator added:

- **A timeout counts toward a service's "sends failed" as a refusal does** (the operator, 2026-11-12).
- **After a rebuild of the notifier, its count of rebuilds in vain resets only once every service has had 3 sends
  without a bug** (each service's bugs rule healthy again, D15). A community service a lost-media node seldom notifies
  can take weeks, so later, unrelated bug episodes count in vain, and after three the notifier is not rebuilt again; it
  still sends. The operator, 2026-11-17: "A", one bugs rule per service as appendix A says, rather than one bugs rule
  on a single notifier part. Raised by block 50's teammate as a class 2 question.
- **A bug on one service rebuilds every service's apprise objects**: the notifier is one object.
- **Two URLs of the same scheme and audience swapped in the configuration swap their names** (`... 2`).
- **A webui rebuild whose port is held elsewhere does not raise**: it costs three rebuilds in vain, then the webui is
  not restarted again (the first stack's answer 25, kept).
- **An intermittent bug never turns its rule failing**, and **the rules start unknown after a restart of the crawler**
  and a part's bugs rule after each rebuild, as in lot 4b4.

## What was built, block by block

| # | PR | Branch | Block | Lines, files |
|---|---|---|---|---|
| 10 | #791 | `feat/webui-thread-watch` | the webui's thread watched every minute, the webui rebuilt (the spec's blocks 10 and 20) | 761, 19, accepted |
| 30 | #792 | `feat/notification-sends-recorded` | each send recorded on the notifier's part, the notifier rebuilt (the spec's blocks 30 and 40) | 658, 21, accepted |
| 50 | | `feat/notification-services-rules` | the notifier lists its services and sends to each of its audience | 487, 16 |
| 53 | | (the lead cuts it) | one part per service, and `NotifierContract` | 292, 18 |
| 90 | | `docs/lot-4b5-wrap` | closing block | |

- **Past a bound, accepted by the operator**: blocks 10 and 20 merged, and 30 and 40, rather than carry code from one
  block to the next ("reco ok, b", 2026-11-17); block 30 at 20 files ("A", 2026-11-17), then at 21 with
  `test_amule_client_works.py`'s call of `node_restart_policy`, its `parts_without_works` kept required ("A",
  2026-11-17).
- **Block 50 cut in two**: written as one block, it came to 604 lines and 21 files without the contract; the operator
  took the cut into 50 and 53, the contract in 53 rather than a block 55 of tests alone ("reco ok", 2026-11-17).
- **Departures, per block**:
  - **10**: the spec's blocks 10 and 20 merged; the first commit's transitional `components_restarting_nothing`
    removed with its tests, `RestartPolicy` unchanged from `main`. `amule_client_restart_policy` becomes
    `node_restart_policy`. `Component.client_name` is `ClientName | None`; the alerter gains `_client_of`. The watch's
    period is its own constant (`_WATCH_PERIOD`), not `STATUS_PERIOD`. Names: the work `webui thread watch`, its part
    and its `Restartable` `webui`. `WebuiRestartable` takes `works_over`, like the client's. Appendix B's "Webui" row
    held on a real uvicorn thread without the supervisor; the chain from watch to rebuild on virtual time over
    `FakeRestartable`. Glossary `webui thread watch`; `architecture.md` §3, §10.1, §10.2, the code table.
  - **30**: the spec's blocks 30 and 40 merged. `NotificationRefusedError`, raised by the apprise notifier, comes here
    (the dispatcher's branch would have no raiser otherwise). A `TimeoutError` of the notifier's own is a bug (the
    dispatcher bounds a coroutine that returns the notifier's exception). `NotifierRestartable` typed on
    `AppriseNotifier`, so `tach.toml` stays as it is (the lead). Names: `SENDS_FAILED`, `notifier_component()`
    (`notifier`, replaced in block 53), `CurrentNotifier`, `CheckRecorder`, `parts_without_works`. Glossary `sends
    failed`, `notification refused`; `architecture.md` §10's E-D13 sentence, §10.1, §10.2, the code table.
  - **50**: names: `NotificationService` (`scheme`, `audience`, `ordinal`), the parts `notifier <service>`. The
    refusals' messages `the service refused it (<status>)` and `apprise could not load its URL`. The log lines drop
    the audience, which the service's name carries. The scheme read in lower case. The services of an audience sent
    to together (the draft's `TaskGroup`), recorded once every send has ended. `FakeHeldNotifier` holds the services
    of `held`, every one by default; `FakeApprise` answers its `status` and records the URL alone, the adapter adding
    each URL without a tag. Glossary `notification service`; `architecture.md` §10.1, the code table.
  - **53**: the dispatcher iterates its own map of services to parts, never the current notifier's `services()`, so
    it never meets a service it has no part for. `notification_service_components` replaces `notifier_component`.
    `NotifierContract` in this block, five doubles exempted (`FakeRaisingNotifier`, `FakeHangingNotifier`,
    `FakeHeldNotifier`, `FakeSlowCommunityNotifier`, `FakeTimedNotifier`); `FakeNotifier` gains `refusing`. Glossary
    `component`, `bugs rule`, `sends failed`, `notification service`; `architecture.md` §10.1, §10.2, the code table.
- **Class 1**: block 10's unread `run_state_store` parameter of `_start_webui` dropped. None in blocks 30, 50, 53.
- **Class 2 questions**: block 10, the transitional list or the merge of blocks 10 and 20: "reco ok, b". Block 30, the
  file bound twice: "A", "A". Block 50, the bound past 20 files without the contract: the cut into 50 and 53, "reco
  ok"; and the count of rebuilds in vain with one bugs rule per service: "A" (Accepted limits). All 2026-11-17.

## The holistic review's findings, and their exits

For the closing block: the review runs once block 53's pull request is open.

## The tests watched failing

Each behaviour test watched failing on its assertion, over a stub of its code, the rest of `src` as the block left it,
`__pycache__` cleared after each change; a `KeyError`, `ValueError` or `IndexError` the code under change raises is
named as such. Blocks 10 and 30 in full in their reports (#791, #792); one line per behaviour here.

| Block | Test | Stub | Failure |
|---|---|---|---|
| 10 | `test_work_components.py`: the webui's part, its name and its bugs | the part named `""`; without `BUGS` | `At index 0 diff: '' != 'webui'`; `KeyError: HealthRule(name='bugs', ...)`, not an assertion |
| 10 | `test_health_alerter.py::test_a_client_s_rule_on_a_part_of_no_client_raises` (2) | the alerter before `_client_of` | `Failed: DID NOT RAISE ValueError` |
| 10 | `test_webui_thread_watch.py`: an ended thread a bug, a minute's wait, its name | a watch finding the thread alive; no wait; named `""` | `Failed: DID NOT RAISE WebuiThreadEndedError`; `assert [] == [datetime.tim...a(seconds=60)]`; `assert '' == 'webui thread watch'` |
| 10 | `test_webui_thread_watch.py`: rebuilt at the third watch; three in vain then no more | the watch finding the thread alive | `assert [] == [240.0]`; `assert [] == [180.0, 360.0, 540.0]` |
| 10 | `test_webui_restartable.py`: the contract, the old thread stopped, serving again, the close | a rebuild building nothing; a close stopping nothing | `assert <...UvicornServerThread ...> is not <...>`; `assert [True] == [False, True]`; `assert [False] == [False, True]`; `Left contains one more item: <Thread(webui, ...)>` |
| 10 | `::test_a_rebuild_on_a_port_held_elsewhere_raises_nothing_and_its_watch_finds_it_ended` | the watch over a thread always alive | `Failed: DID NOT RAISE WebuiThreadEndedError` |
| 10 | `test_node_restart_policy.py::test_bugs_on_the_webui_s_part_rebuild_the_webui_alone` | every part mapped to the first object | `assert (0, 1) == (1, 0)` |
| 10 | `test_uvicorn_server_thread.py::test_its_thread_is_alive_while_it_serves_and_no_more_once_stopped` | `is_alive` always `True` | `assert (True, True) == (True, False)` |
| 10 | `test_crawler_composition_wiring.py`, the time limits and the parts | mutation: the watch left out of the works | `Right contains one more item: 'webui thread watch: time limit 300 s'` |
| 30 | `test_notification_sends.py`: the rule's thresholds, the part's name | `SENDS_FAILED` at 1 of 1, named `""` | `At index 0 diff: <HealthState.FAILING: 'failing'> != None`; `'' != 'notifier'` |
| 30 | `test_observability_dispatcher.py`: a send that worked, a refusal, a timeout, a bug | a dispatcher recording nothing, the old warning line | `assert [] == [_Check(compo...tected=False)]`; `'notification community failed (...)' != 'notifier: community notification not sent: ...'`; `level: 'warning' != 'error'` |
| 30 | `::test_a_timeout_error_the_notifier_raises_itself_is_a_bug_not_a_timeout` | the same; mutation letting the notifier's `TimeoutError` through | `assert [] == [_Check(...)]`; `At index 0 diff: _Check(... detected=False) != _Check(... detected=True)` |
| 30 | `::test_refused_sends_and_sends_past_their_timeout_fail_the_notifier_s_sends` | the same | `At index 0 diff: <HealthState.UNKNOWN: 'unknown'> != <HealthState.FAILING: 'failing'>` |
| 30 | `::test_each_send_goes_to_the_notifier_current_when_it_starts` | mutation: the notifier read once, at construction | `assert (0, 0) == (1, 1)` |
| 30 | `test_health_alerter.py`: "sends failed" sends nothing (3) | the alerter as block 10 left it | `ValueError: notifier, sends failed: no alert for this rule`, not an assertion |
| 30 | `test_apprise_notifier.py::test_a_real_apprise_whose_service_refuses_the_send_raises_a_refusal` | the adapter as `main` has it | `Failed: DID NOT RAISE NotificationRefusedError` |
| 30 | `test_notifier_restartable.py`: the contract, the next send to the latest | a rebuild keeping the old notifier | `assert <...AppriseNotifier ...> is not <...>`; `IndexError: list index out of range`, not an assertion |
| 30 | `test_node_restart_policy.py`: the notifier's part, a notifier raising at every send | the parts without works mapped to the client | `assert (1, 0, 0) == (0, 0, 1)`; `assert (3, 0, 0) == (0, 0, 3)` |
| 50 | `test_notification_sends.py::test_a_service_is_named_by_its_scheme_and_its_audience_a_second_alike_by_its_ordinal` | `__str__` returning `"stub"` | `At index 0 diff: 'stub' != 'discord community'` |
| 50 | `test_apprise_notifier.py`: the services listed, the lower case and `unknown` scheme, none without a URL | `services()` listing one service whatever the configuration | `Right contains 2 more items, first extra item: NotificationService(scheme='ntfy', ...)`; `Right contains one more item: 'unknown operations'`; `Left contains one more item: NotificationService(scheme='discord', ...)` |
| 50 | `test_apprise_notifier.py`: one apprise object per URL, per node | `notify` keeping the two groups of each node | `At index 0 diff: (['discord://x', 'ntfy://y'], 2) != (['discord://z'], 1)`; `At index 1 diff: ('p2pwatch - titar-node-1', 2) != ('p2pwatch - titar-node-2', 1)` |
| 50 | `test_apprise_notifier.py`: the node prefix per service, each kind's title without it (6) | the same | `At index 2 diff: '[titar-node-1] 📥 Download' != '📥 Download'`; `assert '[titar-node-1] 🔎 Notify' == '🔎 Notify'`, and each kind alike |
| 50 | `test_apprise_notifier.py`: a refusal's message; a URL apprise cannot load | the same | `- a service refused it (FAILURE, FAILURE) + the service refused it (FAILURE)`; `Failed: DID NOT RAISE NotificationRefusedError` |
| 50 | `test_observability_dispatcher.py::test_a_notification_goes_to_each_service_of_its_audience_each_send_recorded` | the dispatcher sending to the audience's first service | `Right contains one more item: <Audience.COMMUNITY: 'community'>` |
| 50 | `::test_no_send_is_recorded_before_every_send_of_the_notification_has_ended` | the same | `assert (False, 1, [...]) == (True, 1, [])` |
| 50 | `::test_a_notification_whose_audience_has_no_service_sends_and_records_nothing` | the same | `At index 1 diff: [_Check(... detected=True)] != []` |
| 50 | the refusal's, the timeout's and the bug's log lines (3) | the block 30 lines | `'notifier fake community: community notification not sent: ...' != 'notifier fake community: notification not sent: ...'`; the bug line alike |
| 50 | `::test_the_services_of_an_audience_are_sent_to_together_within_one_timeout`; the held test | passes on the first stub (one service sent to); mutation: the sends in series, each recorded as it ends | `assert 10.0 == 5.0`; `At index 2 diff: [_Check(...), _Check(...)] != []` |
| 53 | `test_notification_sends.py::test_each_service_has_a_part_of_its_own_named_after_it_and_by_no_client` | each part named `notifier` | `At index 0 diff: (NotificationService(...), 'notifier', None, None) != (..., 'notifier discord community', None, None)` |
| 53 | `test_observability_dispatcher.py`: each send on its service's part; the held test's parts | the dispatcher recording every send on its map's first part | `At index 2 diff: _Check(component=<...Component object at 0x...>, ...) != _Check(component=<...Component object at 0x...>, ...)` (2) |
| 53 | `::test_one_service_refusing_and_another_timing_out_fail_each_service_s_sends` | written after the code; mutation: every send on the first part | `At index 1 diff: <HealthState.UNKNOWN: 'unknown'> != <HealthState.FAILING: 'failing'>` |
| 53 | `TestFakeNotifier::test_a_send_its_service_refuses_raises_notification_refused` | `refusing` taken and ignored | `Failed: DID NOT RAISE NotificationRefusedError` |
| 53 | `TestAppriseNotifier`, the contract's three | pass on the adapter; mutations: the ordinals counted across notifiers; a success read as a refusal | `At index 0 diff: NotificationService(... ordinal=4) != NotificationService(... ordinal=1)`; `NotificationRefusedError: the service refused it (SUCCESS)` and `Failed: DID NOT RAISE NotificationRefusedError` |

- **The guards that pass at once, by design**: block 10's running thread raising nothing and the webui's bugs sending
  no alert; block 30's notifier failing at its third bug, an event without a notification recording nothing, the
  notifier's bugs sending no alert, `NotifierRestartable`'s name; block 53's
  `test_bugs_on_any_notification_service_s_part_rebuild_the_notifier_alone`, block 30's test reshaped, never watched
  failing.
- **Not assertions, as the reports say**: block 10's `KeyError`, block 30's `ValueError` and `IndexError`.

## Section 4's rows, where each is held

| Row | Test |
|---|---|
| The webui's thread dying | `test_webui_restartable.py::test_a_webui_whose_thread_ended_serves_again_once_rebuilt`, on a real uvicorn thread; the chain from the watch to the rebuild, `test_webui_thread_watch.py::test_a_thread_ended_has_the_webui_rebuilt_at_the_third_watch_after` (virtual time, `FakeRestartable`) |
| The notifier raising a bug at every send | `test_node_restart_policy.py::test_a_notifier_raising_a_bug_at_every_send_is_rebuilt_three_times_then_never` (20 sends, a real dispatcher, `NodeHealth`, `node_restart_policy` and `Supervisor`: rebuilt 3 times, then never) |
| One notification service refusing, another timing out, every send | `test_observability_dispatcher.py::test_one_service_refusing_and_another_timing_out_fail_each_service_s_sends` (each service's "sends failed" failing at the third send, each change one log line) |

No test runs a rebuild through `CrawlerComposition`: no fault of the fakes drives the real assembly to a webui's or a
notifier's bug.

## What must not change

For the closing block: the matching comparison, `deploy/matcher.yml` and `validate-config`, as lot 4b4's handoff ran
them; the healthy node's notifications and a channel's search cadence at the release candidate.

## The lot's counts

For the closing block: fix-backs, cascaded rebases, runs re-triggered, bodies called unreadable. Known when drafted: the
blocks re-cut once before any push (block 50 into 50 and 53, the lead's rewrite).

## For lot 7 (the operator pages)

- The webui's lines: `bug in webui thread watch` each minute while its thread has ended (error, with its trace);
  `webui, bugs: <from> to <to>`; `restarting webui: bugs in webui`; `webui rebuilt`; `webui not restarted again: 3
  rebuilds in vain`. The first look writes `webui, bugs: unknown to healthy` at 60 s.
- The notifications' lines, per service, `notification <audience> failed (<error>)` gone: `notifier discord community:
  notification not sent: the service refused it (FAILURE)`, `...: apprise could not load its URL`, `...: past its
  timeout of 5 s` (warnings); `bug in notifier discord community, sending a notification` (error, with its trace);
  `notifier discord community, sends failed: <from> to <to>` and `..., bugs: ...`; `restarting notifier: bugs in
  notifier discord community`. A refusal by a service (a webhook's 4xx) is logged now, and a URL apprise cannot load
  is a refusal at each send, where it was skipped in silence.
- A notification goes to every service of its audience together: one `notification_timeout_seconds` per
  notification, whatever the number of services.

## Pitfalls learned

- **Right after a failed bind, `is_alive()` can still read true for an instant**: the thread sets its event in its
  `finally`. A test waits for the thread with `close()` before the watch runs (block 10).
- **Stopping a thread never started raises** (`Thread.join`): the composition starts the first webui thread before any
  rebuild can come (block 10).
- **Recording nests**: an alert's send records on a service's part inside `NodeHealth.record`, so that change reaches
  every subscriber before the outer one reaches the subscribers after `HealthAlerter`. No alert names the services'
  rules, which bounds it; lot 4c's alerts on these parts must not be sent through the notifier (block 30).
- **The restart policy indexes its parts directly**: a test wiring a policy beside a dispatcher recording on the same
  `NodeHealth` must map every service's part, or the first change under a bugs rule raises a `KeyError` (block 30).
- **`node_health` is read by the composition's callback before it is assigned**: `NodeHealth` is built on the next
  statement, and nothing dispatches in between (block 30).
- **A service's sends are recorded once every send of the notification has ended**: a recording that raises inside the
  `TaskGroup` would cancel the other services' sends (blocks 50, 53).
- **The services' parts are built from the first notifier's services**: a rebuilt notifier must list equal services,
  which the same configuration guarantees and `NotifierContract` states; the dispatcher iterates its own map, so a
  service it has no part for is never sent to (block 53).
- **`FakeNotifier.calls` keeps `(audience, notification)`**: a test needing the service reads the checks recorded on
  its part (block 50).
- **`enum` is not among the core's imports** (`application-imports`): a closed set of values there is a `Literal`
  (block 50).
- **The contract's `pytestmark = pytest.mark.asyncio` warns on its synchronous test**: mark the async tests one by one
  (block 53).
- **A test cancelling mid-send must not wait on an event the stub never sets**: the held test reads its state after a
  few yields, so a stub fails it on its assertion instead of hanging (block 50).
- **A mutation leaves a stale `.pyc`**: delete the module's `__pycache__` after each (every block).

## Not validated

- Nothing ran against a real node: no webui thread ended on a node, no rebuild through `CrawlerComposition`, no real
  apprise notifier rebuilt, no real webhook refusing (the refusal test uses apprise's `json://` against a closed local
  port; the unloadable URL a real apprise given `discord://x`), no two real services of one audience.
- **Integration suites**, against `p2pwatch-amule:dev` (built 2026-11-16, no change under `packages/amule` since), a
  fresh daemon each run, `-p 14711:4711`, `P2PWATCH_TEST_API_HOST=127.0.0.1 P2PWATCH_TEST_API_PORT=14711
  P2PWATCH_TEST_API_PASSWORD=indexer-api-test`: `orchestration_integration` 1 passed
  (`test_real_loop_runs_one_search_and_stops`) at block 10's `538a5f11` and `415d7488`, block 30's `1f4406b4`, and at
  block 53's tip (2026-11-17). `api_integration` and `download_integration` did not run: no adapter of aMule changed.
- The matching comparison on the real catalog (What must not change).

## `BACKLOG.md`

The closing block deletes the sub-entry 4b of "v5 release readiness" (the spec's section 6): lot 4b is whole once this
lot merges. The lot adds nothing.

## Left for the closing block

- The holistic review's findings fixed, each with its exit here.
- `BACKLOG.md`'s sub-entry 4b deleted.
- The first stack, #718 to #754, closed unmerged (the spec's preamble), and its branches.
- This handoff corrected: the counts, What must not change, the holistic table, the blocks' pull request numbers.
- The spec's `(Corrected: ...)` beside what the lot changed after its approval: section 5's rows 10 to 50 (the merges,
  the cut into 50 and 53, the contract in 53), appendix A's lot 4b5 rows.

## Next step

The operator reads and merges the stack, rebased onto `main` if it moved. No release: v5 ships after lots 4c to 7 and
their release candidates.

Then lot 4c, what the operator reads of health (the graph of parts, one alert per root cause, the health endpoints, the
metrics, the Node page): its spec, drafted in `agents/specs/2026-11-09-v5-fault-isolation.md`, is to be rewritten on
this spec's names (`Component`, `HealthRule`, `NodeHealth`, `RestartPolicy`, `NotificationService`), its own Discuss
and Spec first. Its alerts on the notification services' parts must not go through the notifier.

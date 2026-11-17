# Handoff: v5 lot 4b4, the restarts of the aMule client (tier Spec)

Drafted by block 40's teammate from the block reports (#785, #786, #788, the collapsed "Block report" of
each pull request body) and its own, for the closing block to correct, the holistic review's findings
included. Spec: `agents/specs/2026-11-15-v5-lot-4b-health-model.md`, lot 4b4 of its five lots (D19),
decisions D14, D15, D17, D18.

## Current state

- **Every part a turn is recorded on has a bugs rule** (`BUGS`, `domain/work_components.py`): failing once
  3 turns in a row met a bug, healthy again once fewer than 2 of the last 10 did; an expected error is no
  bug. After each turn the supervisor records it on the parts its `SupervisedWork` names: `status reading
  amuled`, `download tracking amuled`, `source tracking amuled`, a search's own part (`search 'keroro'
  amuled kad`) and its channel's (`channel amuled kad`). The aMule client's own part (`client amuled`)
  carries no bugs rule: no turn is its own. No alert names the rule; its changes are log lines.
- **A channel's "searches failed"** (`SEARCHES_FAILED`, beside `channel_component`): each search turn
  records detected for a `SearchFailedError`, not detected for a search that ran, nothing for an
  unreachable client, a refused password or a bug. **Download tracking's "connected to no network"**
  (`CONNECTED_TO_NO_NETWORK`, beside `download_tracking_component`): each status reading that answered
  records whether no channel is connected, 6 in a row to fail; a node without `download:` records it
  nowhere. Both are log lines alone.
- **The works over the aMule client are built by one class** (`composition/amule_client_works.py`):
  `AmuleClientWorks.over(client)` returns every work over `client` in start order, each recorded on parts
  its constructor built once; `DownloadSteps` holds the download steps that hold no client, built once.
  `keyword_searches` takes each search's part from its caller (`search_component_of`).
- **An object holding state in memory is a `Restartable`** (`application/ports/driven/restartable.py`,
  generic in the works it hands back): `rebuild()` builds its state anew and returns the works over it.
  `RestartableContract` runs on `AmuleClientRestartable` and `FakeRestartable`.
- **`RestartPolicy`** (`application/steps/restart_policy.py`), subscribed to `NodeHealth` after
  `HealthAlerter`, takes only the bugs rule's changes. When one turns failing on a part, it hands the
  supervisor a `RestartRequest` for the object that part is of (`Supervisor.restart`, through the
  `Restarter` callback). Its phases per object: running, restarting (a request out, another part failing
  meanwhile requests nothing), rebuilt (a bugs rule failing again counts that rebuild in vain and requests
  again), given up (after three in vain). Every bugs rule of the object's parts healthy again resets the
  count and the phase. A rebuild that raised counts in vain through `RestartRequest.rebuild_raised()`.
- **The supervisor runs each restart in a task of its own** (`Supervisor._restart`, under a task group of
  the restarts, itself a task of the supervision): it cancels and awaits every work recorded on one of the
  object's parts, has the object rebuilt, then `RestartRequest.rebuilt()` forgets the bugs rule of each
  part (`Component.forget(BUGS)`; the readings' rules keep their checks, so an open alert neither repeats
  nor ends), and the supervisor runs the works handed back. A rebuild that raises records detected on the
  bugs rule of each part and is tried again `WAIT_AFTER_A_BUG` (60 s) later, while the policy allows; an
  `ExpectedError` (a refused password at the new login) is one warning line, anything else a bug with its
  trace. The requests go through an `asyncio.Queue` the supervisor owns, so a request is never lost to a
  missing task group. At the shutdown the restarts are cancelled with the works.
- **`AmuleClientRestartable`** (`composition/amule_client_restartable.py`): its rebuild logs the old
  session out, builds a client (held before its login, so the shutdown closes it even when the login is
  cut), logs it in, its first searches spaced from the latest starts it reads, and returns
  `AmuleClientWorks.over(new client)`. The resource stack closes the client held then (`close()`).
- **The composition** maps every part the first works are recorded on to the client's `Restartable`, so
  no part a turn is recorded on lacks its object; the policy indexes its parts directly. `NodeHealth` is
  built before the works, which record on it, and the policy after them, so `NodeHealth` reaches the policy
  through `RestartPolicyBuiltLater` (`composition/restart_policy_built_later.py`), which raises
  `PartNotBuiltYetError` on a change passed on before it is set.
- **`Component.state(rule)`** reads a rule's state; **`Component.forget(rule)`** forgets its latest checks,
  the rule unknown again with no change of health to pass on.
- **`SupervisedWork`** moved beside `Work` (`application/steps/work.py`).
- **Not yet**: the webui's and the notifier's restarts (lot 4b5).

## Accepted limits

The spec's section 6, those this lot reaches:

- **An intermittent bug, one that never strikes three turns in a row, never turns its rule failing** nor
  writes a health line; its trace is in the log each time.
- **A bug that strikes every time on one keyword rebuilds its client up to three times**, losing the
  searches in flight each time.
- **After three rebuilds in vain that succeeded, the client's works run on**, only the buggy turns
  failing, and the count resets once every bugs rule of its parts is healthy again; after three rebuilds
  that raised, nothing of the client runs until the container restarts (the operator, 2026-11-12).
- **The rules start unknown after a restart of the crawler**, and a part's bugs rule after each rebuild.

## What was built, block by block

| # | PR | Branch | Block | Lines, files |
|---|---|---|---|---|
| 10 | #785 | `feat/health-rule-bugs` | the bugs rule, recorded by the supervisor | 425, 19 |
| 20 | #786 | `feat/health-rules-searches-and-network` | "searches failed", "connected to no network" | 312, 13 |
| 30 | #788 | `refactor/client-works-built-together` | the works over the client built by one class, the parts built once | 790, 7, accepted |
| 40 | | `feat/client-rebuilt` | `Restartable`, `RestartPolicy`, the client rebuilt | 1427, 30, accepted |
| 90 | | `docs/lot-4b4-wrap` | closing block | |

- **Past a bound, accepted by the operator**: block 30 past the line bound ("A", 2026-11-17: the moved
  code counts twice, about 185 lines out of `run_crawler` and 277 into the new module, and its own tests
  311). Block 40 past both on the spec's row (2026-11-12, "reco ok", "ça me semble ok"); it grew to 1427
  lines and 30 files past the 1198 and 21 of its draft: `SupervisedWork`'s move (8 files of imports), the
  holder and its test, `asyncio.Queue` and `asyncio.Task` allowed in the core (the rule and its test), the
  fake's test listed in `pyproject.toml`, `architecture.md` §10.2, the tests written out.
- **Departures, per block**:
  - **10**: `BUGS` and the three parts judged on it alone in `domain/work_components.py`, each built by one
    function beside the rule; the channel's and download tracking's parts gain `BUGS` where they already
    are. The status reading's part is `status reading amuled` (the draft's `status sensor`).
    `keyword_searches` takes the channels' parts and looks each search's up by client and channel. The
    composition writes `<work>: turns recorded on <parts>` at debug level, which a wiring test reads. No
    check on `SupervisedWork`'s components. The refused password's status test also asserts that no turn
    records a bug. Glossary: `bugs rule`; `supervisor` and `time limit` updated; `architecture.md` §10.1.
  - **20**: none in behaviour. `SEARCHES_FAILED` in `domain/status_reading.py`, `CONNECTED_TO_NO_NETWORK`
    in `domain/download/disk_space.py`, each beside its part's function; the composition builds the status
    watcher after download tracking; the draft's unreachable client counted by "searches failed" (its
    holistic MINOR 4) not taken. Class 1: block 10's two search-bug tests read the bugs rule's lines alone.
  - **30**: `keyword_searches` takes `search_component_of`, so a rebuild keeps each search's part (accepted
    by the lead, 2026-11-17). A class rather than "one function": `AmuleClientWorks.over` is the function,
    its constructor builds the parts once. `works_in_start_order` moved into the new module, its test
    renamed `test_amule_client_works_start_order.py`. `tach.toml`: the composition declares the
    `status_reading_writer` and `waker` ports.
  - **40**:
    - `Restartable` is generic, `Restartable[W]`, `rebuild()` returning `Sequence[W]`: a port cannot import
      the steps (tach's layers), where `SupervisedWork` lives.
    - `SupervisedWork` moved from `supervisor.py` to `work.py`: `restart_policy.py` names
      `Restartable[SupervisedWork]` and `supervisor.py` names `RestartRequest`, which would import each
      other otherwise.
    - No public `Supervisor.add` (the spec's "`Supervisor.add` for the rebuilt works", #785's reading
      guide): the object hands its works back to the supervisor, which runs them itself (`_add`). The one
      public method is `Supervisor.restart(request)`, which the policy calls through its `Restarter`
      callback; the request waits in the supervisor's `asyncio.Queue` until the restarts' task takes it.
    - The holder holds the restart policy, not `NodeHealth` and the supervisor (the spec's row, #752): the
      policy is built after the works, whose parts it maps, and the works record on `NodeHealth`, which
      takes the policy as a subscriber. Nothing reaches the supervisor before it is built, since the works
      are handed back rather than added by the object. `RestartPolicyBuiltLater`,
      `PartNotBuiltYetError`.
    - "A component without one refused at construction" is held by construction instead: the composition
      maps every part the works are recorded on to the client's `Restartable`, so none lacks an object; the
      policy indexes its parts directly and checks nothing at construction (the draft's refusal of a part
      without a bugs rule not taken, every work's part carrying it).
    - A rebuild that raises an `ExpectedError` is one warning line (`rebuild of client amuled: <error>`), a
      bug a trace (`bug in the rebuild of client amuled`); both count in vain and record detected on the
      bugs rules, as D15 says of any rebuild that raises.
    - `asyncio.Queue` and `asyncio.Task` added to the core's asyncio names (`core-import-names.yml`, and its
      rule test): the supervisor's queue of requests and its running works' tasks, which a restart cancels.
    - The works recorded on the object's parts are stopped once, before the first attempt, not before each
      attempt (#751's MINOR 1): a rebuild that raises hands no work back, so no work over it runs.
    - From the draft #738 and #751, #752: `StateOwner`, `restart()`, `empty_windows`, `health_of`,
      `useless`, `owner of client amuled` and `FakeStateOwner` become `Restartable`, `rebuild()`,
      `Component.forget`, `Component.state`, "in vain", `client amuled` and `FakeRestartable`; the
      policy's parts deduplicated (a channel's part is recorded on by each of its searches).
    - Glossary: `restartable`, `restart policy`, `rebuild in vain`; `supervisor` updated.
      `architecture.md` §10.2 and the code table.
- **Class 1**: block 20's above; none in blocks 10, 30, 40.
- **Class 2 questions**: block 30's line bound, answered "A" (2026-11-17). Block 40: one raised at its
  report, the status reading's alert cut by a rebuild (Pitfalls), its answer for the closing block to
  record.

## The holistic review's findings, and their exits

For the closing block.

## The tests watched failing

Each behaviour test watched failing on its assertion, over a stub of its code, the rest of `src` as the
block left it, `__pycache__` cleared after each change; a `KeyError` or `ValueError` the code under change
raises is named as such.

| Block | Test | Stub | Failure |
|---|---|---|---|
| 10 | `test_work_components.py`: the rule's thresholds, its 3 parts failing at the third bug | `BUGS` at 1 of 1, each part named `""` | `At index 0 diff: <HealthState.FAILING: 'failing'> != None` |
| 10 | `test_work_components.py::test_two_bugs_in_a_row_between_turns_that_worked_never_fail` | the same | `At index 0 diff: <HealthState.HEALTHY: 'healthy'> != None` |
| 10 | `test_work_components.py`: the 3 names | the same | `At index 0 diff: '' != "search 'keroro mission' amuled kad"`; `'' != 'status reading amuled'`; `'' != 'source tracking amuled'` |
| 10 | `test_status_reading.py::test_a_channel_s_component_fails_at_the_third_bug_in_a_row_of_its_searches`, `test_disk_space.py::test_download_tracking_fails_at_the_third_bug_in_a_row_of_its_turns` | the part without the rule | `KeyError: HealthRule(name='bugs', ...)`, not an assertion |
| 10 | `test_health_alerter.py::test_a_part_failing_or_healthy_again_under_the_bugs_rule_sends_nothing` (9 cases) | the alerter as `main` has it | `ValueError: channel amuled kad, bugs: no alert for this rule`, not an assertion |
| 10 | `test_supervisor.py::test_a_work_meeting_a_bug_at_each_turn_fails_at_its_third_on_each_of_its_parts` | a supervisor recording nothing | `Right contains 2 more items, first extra item: LoggedLine(level='warning', message="search 'keroro' amuled kad, bugs: unknown to failing")` |
| 10 | `test_supervisor.py::test_three_turns_without_a_bug_make_the_work_s_part_healthy`, `::test_turns_cut_at_their_time_limit_count_as_bugs`, the refused password's new assertion | the same | `Right contains one more item: LoggedLine(level='info', message="search 'keroro' amuled kad, bugs: unknown to healthy")`; `... 'hung work, bugs: unknown to failing'`; `... 'status reading amuled, bugs: unknown to healthy'` |
| 10 | `test_keyword_search.py`: a bug on every Kad search, on one keyword's | the same; then a mutation dropping the channel's part | `assert [] == ['channel amu...n to failing"]`; `assert [] == ["search 'ker...n to failing"]`; `At index 0 diff: "search 'keroro' amuled kad, bugs: unknown to failing" != 'channel amuled kad, bugs: unknown to failing'` |
| 10 | `test_crawler_composition_wiring.py::test_each_work_s_turns_are_recorded_on_its_part_and_a_search_s_on_its_channel_s_too` | no debug line | `assert [] == ['status read...l amuled kad"]` |
| 20 | `test_status_reading.py::test_a_channel_s_searches_fail_at_3_refused_in_a_row_and_heal_under_2_in_the_last_10`, `test_disk_space.py::test_download_tracking_fails_at_6_readings_on_no_network_and_heals_under_2_in_the_last_10` | the rule failing at 1 of 1 | `At index 0 diff: <HealthState.FAILING: 'failing'> != None` (both) |
| 20 | `test_health_alerter.py`: the two rules send nothing (6 cases) | the alerter as block 10 left it | `ValueError: channel amuled kad, searches failed: no alert for this rule`, not an assertion |
| 20 | `test_keyword_search.py::test_three_refused_searches_in_a_row_fail_the_channel_and_nine_that_ran_heal_it`, `::test_an_unreachable_client_after_three_refused_searches_leaves_the_channel_failing` | the search recording nothing; a mutation recording not detected for any other exception | `Right contains 2 more items, first extra item: ... 'channel amuled kad, searches failed: unknown to failing'`; `Left contains one more item: ... 'failing to healthy'` |
| 20 | `test_keyword_search.py::test_a_refused_password_or_a_bug_tells_nothing_of_the_channel_s_searches` | a guard; mutations recording not detected, then detected | `... 'searches failed: unknown to healthy'`; `... 'unknown to failing'` |
| 20 | `test_status_watcher.py::test_six_readings_on_no_network_fail_download_tracking_and_nine_on_one_heal_it`, `::test_an_unreachable_reading_tells_nothing_of_the_client_s_networks` | the watcher recording nothing; mutations `any` to `all`, an unanswered reading detected | `Right contains 2 more items`; `... 'connected to no network: failing to healthy'`; `Left contains one more item: ... 'unknown to failing'` |
| 30 | `test_amule_client_works.py::test_the_works_over_a_client_built_anew_send_their_requests_to_it_alone` | `over` building no work; keeping the works over the first client | `assert [] == [('status rea...", True), ...]`; `assert [<Request('PO...t=500')>, ...] == []` |
| 30 | `::test_the_works_over_a_client_built_anew_are_recorded_on_the_parts_built_once` (2 cases) | no work; the parts built anew in each `over` | `assert [] == ['status read...led kad", ...]`; `At index 0 diff: (<...Component object at 0x...>,) != (<...Component object at 0x...>,)` |
| 30 | the status reading's no network and channel, download tracking's disk, on the parts the works are recorded on | each given a part of its own | `AssertionError: assert <...Component object at 0x...> is <...Component object at 0x...>` (3) |
| 40 | `test_component.py`: `state`, `forget` (3) | `state` always unknown, `forget` doing nothing | `assert <HealthState.UNKNOWN: 'unknown'> is <HealthState.FAILING: 'failing'>` (2); `assert None == HealthTransition(... current=<HealthState.FAILING: 'failing'>)` |
| 40 | `test_fake_restartable.py`: the contract's state built anew, the errors raised in turn | the fake's rebuild keeping its state | `assert <object object at 0x...> is not <object object at 0x...>` (2) |
| 40 | the contract's `test_the_works_each_rebuild_hands_back_run_over_the_state_it_built` (fake) | passes on that stub; the works handed back over the state held before | `assert <object object at 0x...> is <object object at 0x...>` |
| 40 | `test_restart_policy.py`: the first restart, no second while one is under way | a policy that never restarts | `assert [] == [<tests.fakes...FakeRestartable ...>]`; `assert 0 == 1` |
| 40 | `test_restart_policy.py`: its log line, no second restart, three then never, one part healthy alone, a raise counted, the forget | a restart at every bugs rule turning failing, no phase, no count, `rebuilt()` doing nothing | `assert [] == [LoggedLine(l..., error=None)]`; `assert 2 == 1`; `assert 1 == 3` (3); `assert [True, True, True] == [True, True, False]`; `assert [<HealthState...G: 'failing'>] == [<HealthState...N: 'unknown'>]` |
| 40 | `test_restart_policy.py::test_every_bugs_rule_of_its_parts_healthy_after_a_rebuild_resets_the_count`, `::test_three_rebuilds_in_vain_then_every_bugs_rule_healthy_then_a_bug_restart_it` | the whole policy, its count never reset | `assert 3 == 6`; `assert 3 == 4` |
| 40 | `test_restart_policy.py::test_rebuilds_that_raised_and_rebuilds_failing_again_share_one_count` | passes on the second stub; mutation: a raising rebuild not counted | `assert 2 == 1` |
| 40 | `test_restart_policy.py::test_bugs_in_another_part_after_a_rebuild_count_that_rebuild_in_vain_too` | passes on the second stub; mutation: only the part that triggered the restart counting it in vain | `assert 4 == 3` |
| 40 | `test_supervisor_restarts.py`: the six tests | `Supervisor.restart` doing nothing | `assert [] == [121.0, 242.0, 363.0]`; `assert ['works over ...tracking cut'] == ['works over ...uild 1 built']`; `assert [] == [121.0, 181.0, 241.0]` (2); `assert [] == [121.0, 181.0]`; `assert [] == [121.0]` |
| 40 | `::test_a_restart_stops_and_awaits_the_works_over_its_object_before_its_rebuild` | mutation: the works cancelled, not awaited | `assert ['works over ...tracking cut'] == ['works over ...uild 1 built']` |
| 40 | `::test_a_rebuild_that_raises_is_tried_again_60_s_later_its_parts_failing_meanwhile`, `::test_a_rebuild_refused_by_amule_is_logged_in_one_line_and_tried_again` | mutation: no wait between attempts | `assert [121.0, 121.0, 121.0] == [121.0, 181.0, 241.0]`; `assert [121.0, 121.0] == [121.0, 181.0]` |
| 40 | `test_amule_client_restartable.py`: the contract's state built anew, the old session out and a new one in, the close of the client held then, a refused login | a rebuild handing back works over the client it holds, building nothing | `assert <...AmuleApiClient object at 0x...> is not <...AmuleApiClient object at 0x...>`; `assert (1, 0) == (2, 1)`; `assert (0, 0) == (1, 1)`; `Failed: DID NOT RAISE ClientAuthError` |
| 40 | the contract's works over the state built, `::test_a_refused_login_raises_and_the_next_rebuild_builds_a_client_anew` | pass on that stub; mutation: the works handed back over the client before the rebuild | `assert <...AmuleApiClient object at 0x...> is <...AmuleApiClient object at 0x...>` (2) |
| 40 | `test_restart_policy_built_later.py`: before it is set, once set | the holder passing nothing on | `Failed: DID NOT RAISE PartNotBuiltYetError`; `assert [] == [<tests.fakes...FakeRestartable ...>]` |
| 40 | `test_status_watcher.py::test_amule_unreachable_fails_the_client_s_rule_and_rebuilds_nothing` | a guard; mutation: an unreachable reading raised as a bug | `assert [120.0, 240.0, 360.0] == []` |
| 40 | `test_status_watcher.py::test_a_rebuild_of_the_client_under_an_open_alert_neither_sends_it_again_nor_ends_it` | a guard; mutation: a rebuild forgetting every rule of its parts | `Left contains one more item: RelayedLogLine(message='amuled kad: off its network for 5 min', ...)` |

- **The guards that pass at once, by design**: block 20's refused password or bug; block 40's
  `test_another_rule_turning_failing_restarts_nothing` (passes on every stub), the unreachable and the
  open-alert tests, shown on mutations above.
- **Not assertions, as the reports say**: block 10's `KeyError` and `ValueError`, block 20's
  `ValueError`: the code under change refusing a rule it did not know yet.

## Section 4's rows, where each is held

| Row | Test |
|---|---|
| A bugs rule failing with no recovery | `test_supervisor_restarts.py::test_a_bugs_rule_failing_with_no_recovery_rebuilds_its_object_three_times_then_never` (rebuilds at 121, 242, 363 s, then none; the works run on); the policy alone, `test_restart_policy.py::test_bugs_failing_again_after_each_rebuild_restart_it_three_times_then_never` |
| A rebuild of the client that raises | `test_supervisor_restarts.py::test_a_rebuild_that_raises_is_tried_again_60_s_later_its_parts_failing_meanwhile` (raises twice, then rebuilt; failing at 150 and 210 s; attempts at 121, 181, 241 s; the new works running), `::test_three_rebuilds_that_raise_give_it_up_its_works_stopped_the_node_running`; the client's side, `test_amule_client_restartable.py::test_a_refused_login_raises_and_the_next_rebuild_builds_a_client_anew` |
| After three rebuilds in vain that succeeded, every bugs rule healthy, then a bug | `test_restart_policy.py::test_three_rebuilds_in_vain_then_every_bugs_rule_healthy_then_a_bug_restart_it` |
| aMule unreachable | `test_status_watcher.py::test_amule_unreachable_fails_the_client_s_rule_and_rebuilds_nothing` |
| A rebuild under an open connectivity alert | `test_status_watcher.py::test_a_rebuild_of_the_client_under_an_open_alert_neither_sends_it_again_nor_ends_it` (the alert at 300 s, the rebuild at 600 s, eight failed readings after it); the forget alone, `test_restart_policy.py::test_a_rebuild_forgets_the_bugs_of_its_parts_and_keeps_their_other_rules` |
| aMule refusing every search on a channel | `test_keyword_search.py::test_three_refused_searches_in_a_row_fail_the_channel_and_nine_that_ran_heal_it`, `::test_an_unreachable_client_after_three_refused_searches_leaves_the_channel_failing` |
| aMule connected to no network | `test_status_watcher.py::test_six_readings_on_no_network_fail_download_tracking_and_nine_on_one_heal_it`; through the parts the composition builds, `test_amule_client_works.py::test_the_status_reading_records_no_network_on_the_part_of_download_tracking` |

No test runs a rebuild through `CrawlerComposition` itself: its wiring tests run the composition with the
policy set, and the parts the policy maps are those of the first works by construction.

## What must not change

For the closing block: the matching comparison, `deploy/matcher.yml`'s diff and `validate-config`.

## The lot's counts

- Fix-backs: 0 so far. Cascaded rebases: 0 so far.
- Runs re-triggered: 0 so far.
- Bodies the operator called unreadable: 0 so far.
- Past a bound, the operator's acceptances: block 30's lines, "A" (2026-11-17); block 40's both, on the
  spec's row.

## For lot 7 (the operator pages)

- A part's health lines for the new rules: `<part>, bugs: <from> to <to>`, `channel amuled kad, searches
  failed: ...`, `download tracking amuled, connected to no network: ...`; none of them alerts.
- The restarts' lines: `restarting client amuled: bugs in search 'keroro' amuled kad` (warning);
  `restarting client amuled again, 1 of 3 rebuilds in vain: bugs in ...` (warning); `client amuled
  rebuilt` (info); `rebuild of client amuled: <error>` (warning) or `bug in the rebuild of client amuled`
  (error, with its trace); `client amuled not restarted again: 3 rebuilds in vain` (error).
- At debug level, at the start: `<work>: turns recorded on <parts>`.
- A rebuild logs aMule's session out and a new one in, and stops the searches in flight.

## Pitfalls learned

- **A part built in a `parametrize` list is built at collection**, credited to no test, which the own-tests
  check refuses: the tests take the building function, behind a callback `Protocol` (block 10).
- **Recording after a turn is outside its time limit**: a `NodeHealth` subscriber raising there ends the
  node; `HealthAlerter` learns each rule without an alert, and the policy's direct index of its parts makes
  a part without an object end it too (blocks 10, 40).
- **A search records on its channel inside the turn**, so a raising subscriber there is a bug of that turn
  (block 20).
- **`Component` defines no `__eq__`**: a list of parts compares by identity (block 30).
- **A port cannot import the steps**: the `Restartable` port is generic in the works it hands back, and
  `SupervisedWork` sits beside `Work` so the policy and the supervisor import without a cycle (block 40).
- **`asyncio.wait` refuses an empty set**: the works a restart stops are awaited one by one, so an object no
  work runs over would restart all the same (block 40).
- **A request handed before the supervision started would find no task group**: the supervisor keeps its
  requests in a queue its restarts' task reads (block 40).
- **The core's asyncio names**: `Queue` and `Task` are now allowed (`core-import-names.yml`); `Event` still
  is not (block 40).
- **A fake's test module under `tests/fakes/` tests no module of `src`**: list it under
  `[tool.coverage_checks] tests_without_unit` in the package's `pyproject.toml` (block 40).
- **A rebuild stops every work over the client, the status reading included**: an alert being sent inside
  the status reading's turn (`HealthAlerter` through `ObservabilityDispatcher.dispatch`, unshielded) is
  cut by a rebuild triggered elsewhere, and its rule, already failing, never sends it again. Reasoned from
  the code, not observed; raised as a class 2 question in block 40's report (block 40).
- **A mutation leaves a stale `.pyc`**: delete the module's `__pycache__` after each (every block).

## Not validated

- Nothing ran against a real node: no rebuild of a real client, no session logged out and in again under
  load, no searches cut mid-flight by a rebuild, no rule's thresholds against a real aMule's timings.
- **Integration suites**, against `p2pwatch-amule:dev` (built 2026-11-16, no change under `packages/amule`
  since), `-p 14711:4711`, `P2PWATCH_TEST_API_HOST=127.0.0.1 P2PWATCH_TEST_API_PORT=14711
  P2PWATCH_TEST_API_PASSWORD=indexer-api-test`: block 40, at `7dd14c89` (2026-11-17), `api_integration` and
  `orchestration_integration` 5 passed (`test_real_login_succeeds`,
  `test_real_login_fails_with_wrong_password`, `test_real_status`, `test_real_search`,
  `test_real_loop_runs_one_search_and_stops`) on a fresh daemon, then 5 passed again on the same one.
  Block 30, `orchestration_integration` 1 passed at `a384706b`. Blocks 10 and 20 ran none: no adapter
  changed. `download_integration` did not run in the lot.
- No wiring test shows the composition handing the status reading download tracking's part (block 20), nor
  a rebuild through `CrawlerComposition` (block 40).
- The matching comparison on the real catalog (What must not change).

## What is left for the closing block

- The holistic review's findings and their exits.
- The answer to block 40's class 2 question (the alert cut by a rebuild), and its fix where it lands.
- #785's reading guide names `Supervisor.add` for block 40: correct it to `Supervisor.restart`,
  `RestartRequest`, `RestartPolicyBuiltLater`, `Component.state`, `Component.forget`.
- The spec's `(Corrected: ...)` beside each claim block 40 departs from (the holder, `Supervisor.add`, the
  refusal at construction), if the lead keeps them.
- `BACKLOG.md` reconciled; the matching comparison; `deploy/matcher.yml`'s diff and `validate-config`; the
  lot's counts.

## `BACKLOG.md`

For the closing block; the sub-entry 4b stays open until lot 4b5.

## Next step

The operator reads and merges the stack, rebased onto `main` if it moved. No release: v5 ships after lots
4c to 7 and their release candidates.

Then lot 4b5, the webui and the notifier (the spec's section 5 and appendix A, "Lot 4b5"): the webui's
thread watched every minute (block 10), the webui's `Restartable` (block 20), each send recorded on the
notifier (block 30), the notifier's `Restartable` (block 40), one part and one rule per notification
service (block 50). Its own stack from `main`, once lot 4b4 has merged. Each `Restartable` there is mapped
in the composition beside the client's; the notifier's parts are recorded by the dispatcher, not by works,
so they are mapped by hand, which this lot's derivation from the works does not cover.

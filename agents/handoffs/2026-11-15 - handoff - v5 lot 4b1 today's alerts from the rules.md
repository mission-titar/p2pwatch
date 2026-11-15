# Handoff: v5 lot 4b1, today's alerts from the rules (tier Spec)

Drafted by block 50's teammate from the block reports (#757, #758, #760, #761, #762, the collapsed "Block report" of
each pull request body). Corrected by the closing block, which also fixed the holistic review's findings
(`.reviews/v5-lot4b1-holistic.md`). Spec: `agents/specs/2026-11-15-v5-lot-4b-health-model.md`, lot 4b1 of its five
lots (D19). The spec replaces lot 4b of `agents/specs/2026-11-09-v5-fault-isolation.md`.

## Current state

- **The node id is resolved first.** The composition resolves it as soon as `local.db` is open, before the webui and
  before the aMule login. A step that writes the id gets it at construction. On 2026-11-15
  (`git grep -l -w 'node_id: NodeId' -- packages/crawler/src/p2pwatch/application/steps`), these are the cataloguer,
  the file judge, the download tracker, the source watcher and `HealthAlerter`. The status loop lost its id with its
  alert timers (block 40), the download decider with the disk alert (block 50). The lifecycle no longer resolves
  anything: it takes the id.
- **The health model** (`domain/health/`, pure). A `Component` is a part of the node whose health is tracked. It
  carries what the alerts name it by: its `client_name`, and its `channel` where it has one. A `HealthRule` judges a
  part from its latest checks: it fails at `fails_at` (a `Detections`, such as 3 among the last 3) and turns healthy
  again under `recovers_under` (such as fewer than 2 among the last 10). It is unknown until it has `fails_at`'s
  checks. A rule that would turn healthy on the detections that made it fail is refused at construction. The model is
  explained in `domain/health/__init__.py` and in section 10.1 of `docs/contributing/architecture.md`.
- **Each kind of component is built by one function beside its rules**: `client_component` and `channel_component`
  in `domain/status_reading.py`, `download_tracking_component` in `domain/download/disk_space.py`. The composition
  and every test builder call them, so a part's name and rules are written once.
- **`NodeHealth`** (`application/steps/node_health.py`) is the one place every check goes through:
  `record(on=..., rule=..., detected=...)`. Each change is one log line, `<component>, <rule>: <from> to <to>`, a
  warning when it turns failing, an info otherwise. It then passes the change to its subscribers in order. Today there
  is one, `HealthAlerter.send`. `Component.record` itself is called only by `NodeHealth` and the domain's tests: the
  ast-grep rule `component-record-through-node-health` refuses any other call.
- **`HealthAlerter`** sends today's alerts from the changes. Turning failing sends the alert. Turning healthy sends its
  end only after a failing state, so a part healthy from its first checks sends nothing. A rule it has no alert for
  raises a `ValueError`, a wiring bug, as a channel rule on a component without a channel does. It takes the node id
  and the download disk's floor (`min_free_bytes`, `None` on a node without `download:`) at construction.
- **The rules, as the composition builds them**:

  | Component | Rule | Fails at | Healthy again under | Recorded by | Alert, then its end |
  |---|---|---|---|---|---|
  | `client amuled` | unreachable | 3 of 3 | 2 of 10 | the status loop | "amuled unreachable for 2 min", then "amuled reachable again" |
  | `channel amuled ed2k`, `channel amuled kad` | not connected | 6 of 6 | 2 of 10 | the status loop | "amuled kad: off its network for 5 min", then "back on its network" |
  | the same | not connectable | 6 of 6 | 2 of 10 | the status loop | "amuled kad: not connectable for 5 min", then "connectable again" |
  | `download tracking amuled` | disk space low | 1 of 1 | 1 of 1 | the download decision, at each free-space reading | "download disk low: under the 10.0 GiB floor (no new download)", no end |

  `CHANNEL_ALERT_AFTER` and `UNREACHABLE_ALERT_AFTER` are derived in `domain/status_reading.py` from each rule's
  readings: (readings - 1) x the status period.
- **A field aMule did not give records nothing.** While aMule does not answer, each channel keeps its latest readings,
  and no channel alert starts or ends. A `connectable` field aMule cannot tell records nothing either.
- **Operator lines write a duration `<seconds> s`**: `unseen by the client for 86400 s`, `cut after 10 s`,
  `did not start within 5 s`.
- **Gone**: the status loop's `_AlertTimer` (blocks 20 to 40), the download decider's `EdgeState` (block 50), the
  lifecycle's `NodeLoop` wrapper (block 10), and `FakeSteppedStatusClient` with the wall clock step test (closing
  block).
- **Not yet**: the supervisor and works (lot 4b2), a bug failing its turn alone (lot 4b3), the bugs rule and the
  restarts (lots 4b4, 4b5). `Component.state(rule)` and `forget(rule)` come with their first reader, in lot 4b4.

## Accepted limits

- **The disk floor is held twice and can be `None` in `HealthAlerter`.** `DownloadDecider` holds it to judge,
  `HealthAlerter` to word the alert; they agree because the composition passes the same value. One alerter serves both
  configurations, with and without `download:`, so its floor is `int | None`, and a disk change reaching it without a
  floor raises. Each other shape costs more than it removes: a second alerter for the disk would have each subscriber
  pass over the other's rules, so neither could raise on a rule it does not know; the floor carried by the disk's rule
  would teach the health model a byte threshold; carried by the component, the same `None` moves into the domain. The
  spec asks for the floor at the alerter's construction (D6, appendix A). The operator agreed, 2026-11-15.
- **One reading's log names a part two ways.** The client is `amuled unreachable` and `client amuled, unreachable:
  ...`; a channel is `status amuled kad: ...` and `channel amuled kad, not connected: ...`. The per-reading lines are
  today's, so the operator sees one change only (D6). This holds until lot 4c rewrites what the operator sees of
  health.

## What was built, block by block

| # | PR | Branch | Block | Lines, files |
|---|---|---|---|---|
| 10 | #757 | `refactor/steps-built-with-node-id` | the node id resolved first, each step that writes it given it at construction | 412, 31 (the lead's first commit included) |
| 20 | #758 | `feat/health-rule-client-unreachable` | the health model's first pieces; aMule not answering its first rule | 592, 17 |
| 30 | #760 | `feat/health-rule-channel-not-connected` | one component per channel, its not connected rule in place of its timer | 343, 10 |
| 40 | #761 | `feat/health-rule-channel-not-connectable` | each channel's not connectable rule, the last alert timer removed | 185, 7 |
| 50 | #762 | `feat/health-rule-disk-space-low` | download tracking's component, the disk's rule, `EdgeState` removed | 297, 18 |
| 60 | | proposed `refactor/health-component-functions` | each component kind built by one function beside its rules; the connectable wiring test | 163, 11 |
| 70 | | proposed `fix/health-alerter-unknown-rule` | an unknown rule raises; `Component.record` guarded; durations in seconds | 47, 11 |
| 80 | | proposed `test/health-tests-hold-their-claims` | the pattern through `Component.record`; the client's health line; D18's words; docstrings | 152, 15 |
| 90 | | `docs/lot-4b1-wrap` | this handoff, `architecture.md`, `BACKLOG.md` | 6, 2 |

- **Past a bound, accepted in the spec's table**: block 10 past the file bound (a constructor argument across 31
  files, the operator on 2026-11-11); block 20 past the line bound (the model's pieces cannot come without their first
  user, "On fusionne les paires de blocs", 2026-11-11).
- **The closing block split in four** (60, 70, 80, 90): its fixes in one block measured 368 lines and 36 files, past
  the file bound. Each part ran `uv run poe check` green at its own tip.
- **Departures, per block**:
  - **10**: none. One test pruned: `test_search_task_runner.py`'s node id test, since the runner no longer handles
    the id. The glossary's `step` line now reads "a piece of the program the composition builds, behind no driving
    port".
  - **20**: `Component.state(rule)` not added, since nothing in `src` reads it yet and vulture refuses it. The status
    loop records after it has published the reading and sent `ClientUnreachable`, the order the old timer had.
  - **30**: the status loop iterates the components it is given, not the channels of the reading, so a boot with
    aMule down writes one "unknown" debug line per channel where `main` wrote none. A channel the reading lists without
    a component is ignored. `CHANNEL_ALERT_AFTER` moved to `domain/status_reading.py`. `docs/operate.md`'s sentence on
    an unknown reading took the first stack's commit 38339008, not #750's diff, which does not touch `operate.md`.
  - **40**: `StatusLoop` lost its `node_id`, and `test_every_alert_carries_the_node_id_the_loop_is_built_with` was
    pruned, since the alerter's tests check the node id on every alert. The two channel rules share their 6
    (`_CHANNEL_DETECTED_IN_A_ROW`); `HealthAlerter` maps each channel rule to the field its alert names.
  - **50**: the rule is in a new `domain/download/disk_space.py`. `DownloadDecider` lost its `node_id`. `HealthAlerter`
    takes `min_free_bytes: int | None` (Accepted limits). The draft #741's other changes were not taken: they sit on
    the restart policy, the bugs rule and the works, which this lot does not have.
  - **60 to 90**: `uvicorn_server_thread.py`'s and the composition's duration lines change no test, since their tests
    use fractional values (`0.05`, `0.01`) that `%s` and `%g` print alike. The CLI test's fake message follows the new
    form (`cut after 10 s`). `checks_kept` and the two status reading functions gained their own tests, which the
    gate's own-tests check asks for.

## The holistic review's findings, and their exits

1 MAJOR, 14 MINOR; every one fixed in the lot but two accepted limits.

| Finding | Exit |
|---|---|
| MAJOR: the rules a component holds are tied to nothing | fixed (60): one function per component kind; `test_a_reading_of_both_channels_connected_and_connectable_records_every_rule` |
| `architecture.md`'s end of an alert, its line 775, the handoff's "no other sentence" | fixed (90) |
| durations `<seconds> s` (row #750) | fixed (70), the troubleshooting quote included |
| the client's health line missing from the status loop's acceptance test | fixed (80) |
| the wall clock step test cannot fail | fixed (80): deleted, with `FakeSteppedStatusClient` |
| the pattern test on its own copy of the window | fixed (80): driven through `Component.record` in `test_component.py` |
| block 50's TDD departure | fixed (90): re-watched against block 40's tip, below |
| `HealthAlerter`'s unknown rule sends nothing | fixed (70): it raises |
| the disk floor held twice, its `None` branch | accepted limit (Accepted limits), the operator's choice |
| `Component.record` public | fixed (70): the ast-grep rule `component-record-through-node-health` |
| the three "later" sentences | fixed (80, 90): dropped |
| D18's words | fixed (70, 80): `test_the_client_healthy_again_sends_reachable_again`, `test_a_channel_failing_for_four_minutes_never_alerts`, "would turn healthy on the detections that made it fail", the two edited lines reworded |
| `disk_space.py`'s docstring, the spec numbers in edited docstrings | fixed (60, 80) |
| one reading's log naming a part two ways | accepted limit (Accepted limits), until lot 4c |
| `BACKLOG.md`'s lot 4c entry | fixed (90): it names D12 of the umbrella spec and its draft |

## The tests watched failing

One line per new behaviour; the block reports hold every case.

| Block | Test | Failure before the code |
|---|---|---|
| 10 | `test_a_new_node_records_its_id_even_when_amuled_refuses_its_password`, on `main`'s source | `assert None is not None` |
| 20 | `tests/domain/health/`, on `Detections` and `record(rule=..., detected=...)` | `ImportError: cannot import name 'Detections' from 'p2pwatch.domain.health.health_rule'` |
| 20 | the first behaviour tests of the sample #756 | `ModuleNotFoundError: No module named 'p2pwatch.application.steps.health_event_translator'` |
| 30 | the alerter's channel cases | `assert [] == [RelayedLogLine(message='amuled kad: off its network for 5 min', ...)]`; `Failed: DID NOT RAISE ValueError` |
| 30 | the end at the ninth reading back on | `(360.0, ... 'amuled kad: back on its network') != (840.0, ...)` |
| 30 | every channel sampled at each reading | `'status amuled ed2k: connected yes, connectable yes' != 'status amuled ed2k: connected unknown, connectable unknown'` |
| 40 | the health log line | `LoggedLine(level='warning', message='channel amuled kad, not connectable: unknown to failing') in [...]` |
| 40 | the end at the ninth connectable reading | `(360.0, ... 'amuled kad: connectable again') != (840.0, ...)` |
| 40 | an unknown field records nothing | `assert [] == [(360.0, ... 'amuled kad: not connectable for 5 min')]` |
| 50, re-watched | the disk's dips without the free space, on block 40's code | `RelayedLogLine(message='download disk low: 5.0 GiB free, under the 10.0 GiB floor (no new download)', ...) != RelayedLogLine(message='download disk low: under the 10.0 GiB floor (no new download)', ...)` |
| 50, re-watched | the floor wired from `crawler.yml`, on block 40's code | `assert 'download tracking amuled, disk space low: unknown to failing' in [...]` |
| 50, re-watched | the disk's rule, on block 40's code | `ModuleNotFoundError: No module named 'p2pwatch.domain.download.disk_space'` |
| 70 | an unknown rule raises | `Failed: DID NOT RAISE ValueError` |
| 70 | the loss line in seconds | `... unseen by the client for 3600 s: marked failed') in [LoggedLine(... 'unseen by the client for 3600.0s: marked failed')]` |
| 60 | the connectable wiring test, `CHANNEL_NOT_CONNECTABLE` dropped from `channel_component` | `KeyError: HealthRule(name='not connectable', ...)` |
| 80 | the pattern through `Component.record`, its window cut to `fails_at`'s checks | `At index 2 diff: (8, <HealthState.HEALTHY: 'healthy'>) != (129, <HealthState.HEALTHY: 'healthy'>)` |

- **Block 40 watched its failures with the removed argument restored for one run**: a constructor argument removed
  masks every behaviour failure of a suite behind a `TypeError`.
- **Block 50's three behaviours, re-watched by the closing block**: block 50 had watched its tests fail only on a
  missing module or a `TypeError`, then mutated its finished code. The closing block ran block 50's tests over block
  40's `src` (`git checkout feat/health-rule-channel-not-connectable -- packages/crawler/src`), the test support of
  block 40 with one ignored `health_logger` parameter as the only bridge. The two behaviour tests failed on their
  assertions (the rows above). The disk rule's own tests can only fail at import there, the module being new; its
  behaviour, healthy at the first good reading, is what makes the dips test alert twice.
- **Not watched failing**, since `main` behaves the same, as the acceptance rows say: six readings off, one unanswered,
  six off (block 30); the not connectable alert alone at the sixth of ten readings (block 40). The connectable wiring
  test and the pattern test hold behaviour the lot already had: each was watched failing on a mutation (rows 60, 80).

## Section 4's rows, where each is held

| Row | Test |
|---|---|
| aMule unanswering for three readings | `test_status_loop.py::test_unreachable_alerts_at_two_minutes_and_ends_at_the_ninth_answer`, its alerts and `client amuled, unreachable: unknown to failing` in the health log |
| aMule answering again after that alert | the same status loop test, the end at 660 s |
| A channel not connected for six readings | `test_status_loop.py::test_off_the_network_alerts_whatever_the_client_and_channel` |
| Kad not connectable and connected, reading after reading | `test_status_loop.py::test_not_connectable_from_the_first_reading_alerts_at_five_minutes_once` |
| Six failed readings, one unreachable, six failed again | `test_status_loop.py::test_an_unreachable_reading_between_two_runs_off_the_network_ends_nothing` |
| The pattern `000111` repeated, then ten not detected | `test_component.py::test_3_checks_not_detected_then_3_detected_over_and_over_fail_once_until_they_stop` |
| The disk below its floor twice | `test_download_decider.py::test_the_disk_alerts_once_per_dip_under_its_floor_without_the_free_space`; the floor from the config in `test_crawler_composition_wiring.py::test_a_disk_under_its_floor_alerts_with_the_floor_from_the_config` |

## What must not change

| Check | Result |
|---|---|
| The matching decisions on the real catalog | **not run**: the umbrella's comparison (`agents/reference/2026-11-04-v5-audit-instruments/matching/`) reads the operator's `catalog.db` in `/home/geoffrey/Projets/mulewatch/data`, outside the repository. The lot touches no matching code: `git diff --name-only origin/main -- packages/crawler/src/p2pwatch/domain/matching packages/crawler/src/p2pwatch/adapters/driven/config` lists nothing, and the gate's golden corpus passes |
| `deploy/matcher.yml` and its keys | `git diff --stat origin/main -- deploy/matcher.yml deploy/targets.yml` empty; `validate-config` on `deploy/`, its environment variables set to placeholders: `Config valid` |
| A healthy node's notifications, a channel's search cadence | at the release candidate |

## The lot's counts

- Fix-backs: 0. Cascaded rebases: 0.
- Runs re-triggered: 1, block 50's, by the push of this handoff's draft. Fewer than the lot's blocks.
- Bodies the operator called unreadable: 0.

## For lot 7 (the operator pages)

- The ends of "unreachable", "not connected" and "not connectable" come about nine readings after the recovery.
- While aMule is unreachable, no channel alert starts or ends: the channels keep their latest readings.
- The disk alert no longer gives the free space. The free space stays in `/metrics` and in the debug log.
- One new log line per change of health, such as `client amuled, unreachable: unknown to failing`.
- A boot with aMule down writes one "unknown" debug line per channel (block 30).
- The durations of the operator lines read `<seconds> s`.
- The sentences of `docs/` this lot made false were corrected in it: `operate.md`'s on an unknown reading (block 30),
  `architecture.md`'s on the end of an alert (closing block), `troubleshooting.md`'s quote of the loss line (closing
  block). Nothing went to `docs/migration-4x.md`.

## The operator's decisions in this lot

- **The disk alert drops its free space** (2026-11-15): "Est-ce qu'on a réellement besoin de mesurer, ou l'alerte est
  suffisante ?"
- **The disk floor stays at the alerter's construction, `None` without `download:`** (2026-11-15), an accepted limit.
- The closing findings' exits, as listed above (the lead's choices, 2026-11-15).
- The decisions of 2026-11-11 and 2026-11-12 that this lot applies are in the spec's section 3 and appendix A.

## Pitfalls learned

- **Serena's `rename_symbol` was partial** at each rename of block 20's sample: it reached only the definition, or
  only its own file. Every rename was finished by hand and checked with `git grep -w` (`.claude/rules/serena.md`).
- **A constructor argument removed hides behaviour failures** behind a `TypeError` (blocks 40 and 50). Restore the
  argument for one run, or mutate the finished code, to watch the behaviour fail.
- **A mutation reverted within the second leaves a stale `.pyc`.** Python checks a module's bytecode against its
  source's size and mtime in whole seconds. Block 50's mutation of `disk_space.py` (`among_last=1` to `2`, same size)
  survived its revert in `__pycache__`, and the closing block's first run read `recovers_under` 1 of 2 from it. Clear
  `__pycache__` under `src` after any mutation.
- **The download tests' builder `build_cycle` wires `NodeHealth` and `HealthAlerter`** as the composition does, its
  health lines in a logger of their own (`health_logger`). The tests that assert the steps' exact log lines then see
  no health line.
- **A wiring test can stop the node right after a reading's records**: `_SigtermAtRecord` on the dispatcher's
  `status amuled kad: ...` debug line raises SIGTERM on the loop's thread, and the reading's records end before the
  loop next yields.

## Not validated

- Nothing ran against a real node, a real aMule or a real full disk. The status loop's tests drive it on a fake clock.
- No Docker integration suite ran in this lot; no adapter changed but `uvicorn_server_thread.py`'s log line.
- Block 10's order "before the webui" has no test of its own; the wiring test checks "before the login".
- The matching comparison on the real catalog (What must not change).

## Next step

The lead cuts blocks 60, 70 and 80 under the closing block (their commits are in order on `docs/lot-4b1-wrap`),
rebases the stack onto `main` if it moved, and the operator reads and merges it. No release: v5 ships after lots 4c to
7 and their release candidates. `BACKLOG.md`'s sub-entry 4b stays open until lot 4b5.

Then lot 4b2, the supervisor (the spec's section 5 and appendix A, "Lot 4b2"). Each task the node repeats becomes a
`Work`, and one `Supervisor` runs them all, behaviour unchanged except source tracking's two changes in its block 40.
It is its own stack from `main`, once lot 4b1 has merged.

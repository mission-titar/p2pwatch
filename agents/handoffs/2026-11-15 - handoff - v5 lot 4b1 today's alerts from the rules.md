# Handoff: v5 lot 4b1, today's alerts from the rules (tier Spec)

Drafted by block 50's teammate from the block reports (#757, #758, #760, #761, #762, the collapsed "Block report" of
each pull request body), for the closing block (90) to correct. Spec: `agents/specs/2026-11-15-v5-lot-4b-health-model.md`,
lot 4b1 of its five lots (D19). The spec replaces lot 4b of `agents/specs/2026-11-09-v5-fault-isolation.md`.

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
- **`NodeHealth`** (`application/steps/node_health.py`) is the one place every check goes through:
  `record(on=..., rule=..., detected=...)`. Each change is one log line, `<component>, <rule>: <from> to <to>`, a
  warning when it turns failing, an info otherwise. It then passes the change to its subscribers in order. Today there
  is one, `HealthAlerter.send`.
- **`HealthAlerter`** sends today's alerts from the changes. Turning failing sends the alert. Turning healthy sends its
  end only after a failing state, so a part healthy from its first checks sends nothing. It takes the node id and the
  download disk's floor (`min_free_bytes`, `None` on a node without `download:`) at construction.
- **The rules, as the composition builds them**:

  | Component | Rule | Fails at | Healthy again under | Recorded by | Alert, then its end |
  |---|---|---|---|---|---|
  | `client amuled` | unreachable | 3 of 3 | 2 of 10 | the status loop | "amuled unreachable for 2 min", then "amuled reachable again" |
  | `channel amuled ed2k`, `channel amuled kad` | not connected | 6 of 6 | 2 of 10 | the status loop | "amuled kad: off its network for 5 min", then "back on its network" |
  | the same | not connectable | 6 of 6 | 2 of 10 | the status loop | "amuled kad: not connectable for 5 min", then "connectable again" |
  | `download tracking amuled` | disk space low | 1 of 1 | 1 of 1 | the download decision, at each free-space reading | "download disk low: under the 10.0 GiB floor (no new download)", no end |

  The client's and channels' rules are in `domain/status_reading.py`, the disk's in `domain/download/disk_space.py`.
  `CHANNEL_ALERT_AFTER` and `UNREACHABLE_ALERT_AFTER` are derived there from each rule's readings: (readings - 1) x
  the status period.
- **A field aMule did not give records nothing.** While aMule does not answer, each channel keeps its latest readings,
  and no channel alert starts or ends. A `connectable` field aMule cannot tell records nothing either.
- **Gone**: the status loop's `_AlertTimer` (blocks 20 to 40), the download decider's `EdgeState` (block 50), and
  the lifecycle's `NodeLoop` wrapper (block 10).
- **Not yet**: the supervisor and works (lot 4b2), a bug failing its turn alone (lot 4b3), the bugs rule and the
  restarts (lots 4b4, 4b5). `Component.state(rule)` and `forget(rule)` come with their first reader, in lot 4b4.

## What was built, block by block

| # | PR | Branch | Block | Lines, files |
|---|---|---|---|---|
| 10 | #757 | `refactor/steps-built-with-node-id` | the node id resolved first, each step that writes it given it at construction | 412, 31 (the lead's first commit included) |
| 20 | #758 | `feat/health-rule-client-unreachable` | the health model's first pieces; aMule not answering its first rule | 592, 17 |
| 30 | #760 | `feat/health-rule-channel-not-connected` | one component per channel, its not connected rule in place of its timer | 343, 10 |
| 40 | #761 | `feat/health-rule-channel-not-connectable` | each channel's not connectable rule, the last alert timer removed | 185, 7 |
| 50 | #762 | `feat/health-rule-disk-space-low` | download tracking's component, the disk's rule, `EdgeState` removed | 297, 18 |
| 90 | | `docs/lot-4b1-wrap` | closing block: this handoff corrected, the holistic review's fixes, the matching comparison | |

- **Past a bound, accepted in the spec's table**: block 10 past the file bound (a constructor argument across 31
  files, the operator on 2026-11-11); block 20 past the line bound (the model's pieces cannot come without their first
  user, "On fusionne les paires de blocs", 2026-11-11).
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
    takes `min_free_bytes: int | None`, and a disk change reaching it without a floor raises, as a channel rule on a
    component without a channel does. The draft #741's other changes were not taken: they sit on the restart policy,
    the bugs rule and the works, which this lot does not have.

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
| 50 | the disk's dips, the old wording put back | `AssertionError: assert [(<Audience.O...ode_id='n1'))] == [(<Audience.O...ode_id='n1'))]` |
| 50 | the rule healthy at its first good reading, the rule made to need two | `At index 2 diff: None != <HealthState.HEALTHY: 'healthy'>`; `assert [1, 0, 0, 0, 0] == [1, 0, 0, 1, 0]` |
| 50 | the floor wired from `crawler.yml`, the composition passing `None` | `ValueError: download tracking amuled: no disk floor for its alert` |

- **Block 40 watched its failures with the removed argument restored for one run**: a constructor argument removed
  masks every behaviour failure of a suite behind a `TypeError`.
- **Block 50 departs from strict TDD.** Its tests were written first and watched failing, but only on a missing
  module or a `TypeError` (`HealthAlerter.__init__() got an unexpected keyword argument 'min_free_bytes'`). Their
  behaviour failures were watched afterwards, by mutating the finished code: the three rows above.
- **Not watched failing**, since `main` behaves the same, as the acceptance rows say: six readings off, one unanswered,
  six off (block 30); the not connectable alert alone at the sixth of ten readings (block 40).

## Section 4's rows, where each is held

| Row | Test |
|---|---|
| aMule unanswering for three readings | `test_status_loop.py::test_unreachable_alerts_at_two_minutes_and_ends_at_the_ninth_answer`; the log line in `test_node_health.py::test_the_client_turning_failing_is_logged_as_one_warning` |
| aMule answering again after that alert | the same status loop test, the end at 660 s |
| A channel not connected for six readings | `test_status_loop.py::test_off_the_network_alerts_whatever_the_client_and_channel` |
| Kad not connectable and connected, reading after reading | `test_status_loop.py::test_not_connectable_from_the_first_reading_alerts_at_five_minutes_once` |
| Six failed readings, one unreachable, six failed again | `test_status_loop.py::test_an_unreachable_reading_between_two_runs_off_the_network_ends_nothing` |
| The pattern `000111` repeated, then ten not detected | `test_health_rule.py::test_3_checks_not_detected_then_3_detected_over_and_over_fail_once_until_they_stop` |
| The disk below its floor twice | `test_download_decider.py::test_the_disk_alerts_once_per_dip_under_its_floor_without_the_free_space`; the floor from the config in `test_crawler_composition_wiring.py::test_a_disk_under_its_floor_alerts_with_the_floor_from_the_config` |

## For lot 7 (the operator pages)

- The ends of "unreachable", "not connected" and "not connectable" come about nine readings after the recovery.
- While aMule is unreachable, no channel alert starts or ends: the channels keep their latest readings.
- The disk alert no longer gives the free space. The free space stays in `/metrics` and in the debug log.
- One new log line per change of health, such as `client amuled, unreachable: unknown to failing`.
- A boot with aMule down writes one "unknown" debug line per channel (block 30).
- `docs/operate.md` already says the channels keep their latest readings (block 30). No other sentence of `docs/`
  became false in this lot; nothing went to `docs/migration-4x.md`.

## The operator's decisions in this lot

- **The disk alert drops its free space** (2026-11-15): "Est-ce qu'on a réellement besoin de mesurer, ou l'alerte est
  suffisante ?"
- The decisions of 2026-11-11 and 2026-11-12 that this lot applies are in the spec's section 3 and appendix A.

## Pitfalls learned

- **Serena's `rename_symbol` was partial** at each rename of block 20's sample: it reached only the definition, or
  only its own file. Every rename was finished by hand and checked with `git grep -w` (`.claude/rules/serena.md`).
- **A constructor argument removed hides behaviour failures** behind a `TypeError` (blocks 40 and 50). Restore the
  argument for one run, or mutate the finished code, to watch the behaviour fail.
- **The download tests' builder `build_cycle` wires `NodeHealth` and `HealthAlerter`** as the composition does, its
  health lines in a logger of their own (`health_logger`). The tests that assert the steps' exact log lines then see
  no health line.

## Not validated

- Nothing ran against a real node, a real aMule or a real full disk. The status loop's tests drive it on a fake clock.
- No block report records a Docker integration suite run; no adapter changed in this lot.
- Block 10's order "before the webui" has no test of its own; the wiring test checks "before the login".

## For the closing block

- The holistic review over `git diff origin/main...origin/feat/health-rule-disk-space-low`, its findings and their
  exits.
- The matching comparison (the umbrella's appendix B, "Matching"): 0 decisions differ.
- The lot's counts: fix-backs, cascaded rebases, the runs they re-triggered, and any body the operator called
  unreadable.
- `BACKLOG.md`: the sub-entry 4b stays open until lot 4b5.

## Next step

Lot 4b2, the supervisor (the spec's section 5 and appendix A, "Lot 4b2"). Each task the node repeats becomes a `Work`,
and one `Supervisor` runs them all, behaviour unchanged except source tracking's two changes in its block 40. It is
its own stack from `main`, once lot 4b1 has merged.

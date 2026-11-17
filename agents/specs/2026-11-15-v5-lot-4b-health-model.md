# v5 lot 4b: the health model

Tier Spec. This spec replaces everything about lot 4b in `agents/specs/2026-11-09-v5-fault-isolation.md` (the lot 4
spec, itself lot 4 of the umbrella `agents/specs/2026-11-04-v5-release-readiness.md`, whose D12 it implements): its
decisions, acceptance, blocks and design. The lot 4 spec keeps lot 4a's record and its facts (its appendix C); its lot
4c is to be rewritten on this spec's names once lot 4b has merged.

Why a new spec: the first build of lot 4b, the stack #718 to #754 (33 pull requests), could not be reviewed. It was too
large to read in one go, and its code was written in the old spec's words, readable only with the spec in mind. A
rewritten sample of its second pull request, #756, settled with the operator how the code is written and what its
concepts are named (2026-11-13 to 2026-11-15). This spec keeps the operator's earlier decisions (2026-11-11 and
2026-11-12) and states them with those names. The first stack stays open, read only as a draft, and is closed unmerged
once the last lot below has merged.

## 1. In short

Today an unexpected error anywhere in the crawler (a bug in a Kad search, a refused password) stops the whole node,
webui included, and Docker restarts it into the same error.

This lot gives the crawler a health model. The node tracks the health of each of its parts, such as the aMule client or
one keyword's search on Kad. Each part has rules, such as "aMule does not answer". At each check, the code records
whether the rule detected its case; from its latest checks, the rule says whether the part is healthy or failing. A
supervisor runs every task the node repeats, turn after turn, so a bug fails its own turn and nothing else. An object
whose bugs keep coming back is rebuilt, three times at most. Today's alerts are sent by these rules.

Lot 4c then adds what the operator reads of health: the graph of parts, one alert per root cause, the health endpoints,
the metrics and the Node page.

## 2. What the operator will see

- **A bug in one part no longer stops the node**: a bug in one keyword's search fails that search's turn, and every
  other search, the downloads and the webui go on.
- **An object whose bugs repeat is rebuilt**: the aMule client, the webui or the notifier, three times at most when
  the rebuild repairs nothing.
- **A stuck turn is cut** past its time limit and counted as a bug.
- **Each change of health is one log line**: `client amuled, unreachable: healthy to failing`.
- **Today's alerts start as today and end later**: "amuled reachable again" comes about nine readings after aMule
  answers again, so a flaky client does not alert on and off.
- **The disk alert no longer gives the free space**: `download disk low: under the 10.0 GiB floor (no new download)`;
  the free space stays in `/metrics`, and in the log at debug level.
- **A password refused while the node runs no longer stops it**: the searches fail and the log says why; its own alert
  is lot 4c's.
- **A node restarted within a minute of a search waits before that channel's next search**, as the network asks.
- The operator pages are lot 7's; appendix D lists what they must say.

## 3. Decisions

The decisions are the operator's; where the lead proposed one, the operator accepted it. A draft's docstrings cite the
lot 4 spec's decision numbers, which this spec does not keep.

### The health model

- **D1. Each part of the node is a component, judged by its health rules, each rule over its own latest checks.**
  *One model says "this part has been unwell for a while" for every cause, a network outage or a bug; counting checks
  measures each part at its own pace, where a time window would leave a rarely used part unknown forever.* Lot 4b1.
- **D2. A rule turns failing once it has detected its case often enough, for example 3 times among the last 3 checks;
  it turns healthy again once it detects it less often, for example fewer than 2 times among the last 10; it is unknown
  until it has enough checks.** *Two thresholds stop a repeating pattern from alerting on and off.* The disk's rule
  fails at one detection, as today's disk alert. Lot 4b1.
- **D3. At each check, the code that made it records whether the rule detected its case:
  `record(on=..., rule=..., detected=...)`, the observation a boolean, nothing else passed.** *Turning what a port
  returned into a fact of health is the application's job, so the health model depends on no other part of the code; a
  reading that raises nothing, such as a channel not connected, is written the same way as an error; one call per rule,
  without a branch, keeps the code that checks short.* Lot 4b1.
- **D4. Every check goes through one place, `NodeHealth`, which writes each change of health in one log line, then
  passes it on, in order, to the alerts and to the restarts.** *Six parts of the code record checks (the status
  reading, the download decision, the search turns, the supervisor, the notification dispatcher, the restart policy);
  without one place, each would log and notify on its own.* Lot 4b1.
- **D5. In lot 4b a rule knows one state past healthy: failing.** *Nothing in lot 4b tells "degraded" from "failing":
  the graph and the health endpoints that do arrive in lot 4c, with degraded. What waits for lot 4c with it: an
  intermittent fault, one that never strikes three checks in a row, changes no health and writes no health line; each
  occurrence keeps its own log line.* The "not connectable" alert keeps its name and its start. Lot 4b1.
- **D6. Today's alerts are sent by `HealthAlerter` when a rule changes: the alert when the rule turns failing, its end
  only when it turns healthy after that alert.** *Today's start is kept, so the operator sees one change only, the
  later end; healthy from the first readings sends nothing, as today.* The disk alert has no end, as today, and drops
  its free space (the operator, 2026-11-15: "Est-ce qu'on a réellement besoin de mesurer, ou l'alerte est suffisante
  ?"). Lot 4b1.

### The supervisor

- **D7. Every task the node repeats is a work: a turn, then a wait before the next; one supervisor runs every work.**
  The works: the status reading, download tracking, source tracking, one search per client, channel and keyword, and
  the webui's watch. *One place bounds every turn and judges how it ended, as an OTP supervisor does; the wait is the
  work's own (the backoff, the status period), outside the turn's time limit.* Lot 4b2, the webui's watch lot 4b5.
- **D8. A turn ends in one of three ways: it worked; it met an expected error, logged in one line; or it met a bug, any
  other exception, logged with its trace. An error or a bug fails that turn alone. After a bug, the next turn waits at
  least 60 s.** (Corrected: the works a rebuild hands back take their first turn as at the node's
  start, each after its own wait alone, the closing block of lot 4b4 on 2026-11-17: they are new
  objects, which no bug has met yet.) *The part that must be correct for the rest to fail safely is small (Armstrong); without the wait, a
  bug that strikes at once would rerun at full speed, a trace per turn.* Lot 4b3.
- **D9. Every error a port of the core declares derives from `ExpectedError`; any other exception is a bug.**
  (Corrected: every error a driven port declares, the operator on 2026-11-11, "every failure a driven port declares";
  a driving port's error goes to the command line, never into a turn.) *The
  supervisor tells them apart by their type alone, a new port's error follows the same rule, and an exception nobody
  declared is a bug by construction. No static tool proves which exceptions a library call raises (lot 4 spec,
  appendix C), so each port's contract tests provoke its real failures instead.* Lot 4b3.
- **D10. Each work has a time limit: the sum of the bounds on its turn's path, plus 5 minutes. Past it, the turn is cut
  and counted as a bug.** *A stuck turn then becomes an ordinary bug that says which work and how long (Nygard's
  Timeouts); a limit under that sum would cut a healthy turn.* Lot 4b3.
- **D11. A keyword whose search fails is searched again at its next turn, and a bug never touches its channel's
  backoff.** *The node exists to miss nothing; the backoff measures the network's refusals, and counting our bugs in it
  would slow every keyword for one keyword's bug.* Lot 4b3.
- **D12. A request to aMule lasts 60 s at most, whatever it waits on.** *httpx bounds each phase of a request, never
  the whole, so a server sending its answer byte by byte keeps a call alive past every limit.* Lot 4b3.
- **D13. Each client's latest search starts are kept in `local.db`, so a client built anew, by a restart or at the
  node's start, spaces its first searches from them.** *The spacing is the network's rule, and a new client forgot its
  latest starts; the rows are keyed by client, channel and a scope each adapter chooses, so another network's clients
  fit without change.* Lot 4b3.

### The restarts

- **D14. Every component a turn or a send is recorded on has a "bugs" rule. When one turns failing, the object holding
  that component's state in memory (the aMule client, the webui, the notifier) is rebuilt by the composition.** *A
  restart can only clear memory (a session, a lock, a cache, a thread), and most faults pass when the work runs again
  (Gray); an object built anew is fresh by construction. A network failure is never repaired by a restart, which only
  worsens an outage (the SRE book), so only the bugs rule restarts. A search holds no state, so it is never
  restarted.* Lot 4b4, the webui and the notifier lot 4b5.
- **D15. An object is rebuilt three times at most in vain. A rebuild is in vain when a bugs rule of its components
  detects bugs to failing again before they are all healthy; the count resets once they are. A rebuild that raises
  leaves the object's components failing and is tried again 60 s later, counted in vain.**
  (Corrected: a rebuild raising an `ExpectedError`, such as a refused password at the new login, is
  logged in one warning line, any other exception with its trace, as D8 logs a turn; lot 4b4 block
  40.) *Three echoes OTP's bounded
  restarts: a bug that keeps coming back costs at most three rebuilds, aMule itself untouched.* Lot 4b4, the webui and
  the notifier lot 4b5.
- **D16. A notification already decided is sent even when its turn is cut or its object rebuilt.** *Cutting the turn
  between the decision's write and its send would lose the notification.* Lot 4b3.

### How the lot is written and cut

- **D17. A developer who never read this spec understands the code.** A docstring says what the thing does, with
  today's case as its example, never its place in the mechanism; the model is explained in a few short sentences before
  the code (`domain/health/__init__.py`, `docs/contributing/architecture.md`); each name says what the thing is
  (appendix A, "Names"); a log line names each part once, the same way everywhere. *The first stack was written in the
  spec's words and could not be read without it.* Every lot.
- **D18. The lot's words, each with one meaning: an exception and an error are Python's, what the code raises; a bug
  is an exception nobody expected; detected is what a rule saw or not at one check; failing and healthy are a part's
  state under a rule.** *The first stack mixed failure, outcome, reason and error for overlapping things.* Every lot.
- **D19. Lot 4b is cut into five lots, merged one after the other: 4b1 today's alerts from the rules, 4b2 the
  supervisor, 4b3 a bug fails its turn alone, 4b4 the restarts of the aMule client, 4b5 the webui and the notifier.**
  Each lot is a stack of its own, with its closing block, its holistic review, its handoff, and a reading guide at the
  head of its first pull request (the lot's blocks in order, what each brings, the names it introduces). Each block is
  rewritten from the first stack's as a draft, the first stack's closing fixes folded into the blocks they concern
  (appendix A). *The operator reads and merges a lot before the next one starts; a lot holds at most 19 blocks.* Every
  lot.

## 4. Acceptance

Commands for each row: appendix B.

### Lot 4b1

| Check | After the lot | On `main` |
|---|---|---|
| aMule unanswering for three readings | "amuled unreachable for 2 min", and `client amuled, unreachable: unknown to failing` in the log | the alert alone |
| aMule answering again after that alert | "amuled reachable again" at the ninth answer, not before | at the first answer |
| A channel not connected for six readings | its alert at the sixth reading | the same |
| Kad not connectable and connected, reading after reading | the not connectable alert alone, at the sixth reading | the same |
| Six failed readings, one unreachable, six failed again | no end sent, no second alert | the same |
| The pattern `000111` repeated (`1` detected), then ten checks not detected | failing from the third detection to the end of the pattern, healthy at the ninth of the ten, not before | n/a |
| The disk below its floor twice, two low readings each time | `download disk low: under the 10.0 GiB floor (no new download)` once per dip | the alert with the free space, once per dip |

### Lot 4b2

| Check | After the lot | On `main` |
|---|---|---|
| The behaviour tests of the status reading, download tracking, source tracking and the searches | passing, moved to the works, none removed | passing |
| A channel backed off when the node restarts | its first search after the persisted wait | the same |
| A shutdown during any turn | every work stopped within the shutdown deadline | the same |
| A failed source list read | the next read a full `sources_interval` later | one poll later |

### Lot 4b3

| Check | After the lot | On `main` |
|---|---|---|
| A bug on every Kad search | the eD2k searches go on | the crawler stops |
| A bug on one keyword's searches | that keyword's turns fail, the other keyword's searches go on | the crawler stops |
| A work raising a bug at once, turn after turn | two of its turns never closer than 60 s | the crawler stops |
| A turn that never returns | cut at its time limit, counted as a bug | the task waits forever |
| Ten eD2k keywords queued on the client's lock | no turn past its time limit | n/a, no limit |
| A password refused while the node runs | an expected error each turn, the node running | the crawler stops, at every start |
| aMule sending its answer byte by byte | the request cut at its total bound, an unreachable client | the call never ends |
| A node restarted within a minute of a search start | its next start one spacing after that start | a restart forgets the latest start |
| A turn cut between a decision's write and its notification | the notification sent | n/a |

### Lot 4b4

| Check | After the lot | On `main` |
|---|---|---|
| A bugs rule failing with no recovery | the aMule client rebuilt, three times in vain, then no more | n/a |
| A rebuild of the client that raises | the client's components failing, tried again after 60 s, three times at most, the node running | n/a |
| After three rebuilds in vain that succeeded, then every bugs rule healthy, then a bug | a rebuild again | n/a |
| aMule unreachable | the unreachable rule failing, nothing rebuilt | the status loop alerts, nothing else |
| A rebuild under an open connectivity alert | the alert neither sent again nor ended | n/a |
| aMule refusing every search on a channel | its "searches failed" rule failing, in the log | a warning per failed search, no health |
| aMule connected to no network | download tracking's rule failing, in the log | each channel's not connected alert, nothing for download tracking |

### Lot 4b5

| Check | After the lot | On `main` |
|---|---|---|
| The webui's thread dying | the webui rebuilt and serving again | the webui stays down |
| The notifier raising a bug at every send | the notifier rebuilt, three times in vain at most | a warning per send, the crawl going on, nothing rebuilt |
| One notification service refusing, another timing out, every send | each service's "sends failed" rule failing, in the log | a timeout logged per send, a refusal not logged |

### What must not change

| Check | Observed by |
|---|---|
| The matching decisions on the real catalog | the umbrella's matching comparison (its appendix B, "Matching"): 0 decisions differ, run at each lot's closing block |
| `deploy/matcher.yml` and its keys | `git diff --stat main -- deploy/matcher.yml` empty, `validate-config` on `deploy/` passing |
| A healthy node's notifications | no unreachable, not connected or disk alert during an hour where every status reading shows each channel connected, checked at the release candidate |
| A healthy channel's search cadence | searches per hour on the node at the release candidate, within the lot 4 spec's appendix C range |

## 5. Blocks

Each lot is its own stack from `main`, its blocks numbered by tens. Each block's draft is the first stack's pull
request named in its row; its size is the draft's, measured by the workflow's command against its parent (appendix C).
A block past a bound says why it cannot split, with the operator's acceptance (appendix A).

### Lot 4b1, today's alerts from the rules

| Block | Branch | Content | Draft, its size |
|---|---|---|---|
| 10 | `refactor/steps-built-with-node-id` | the node id resolved first, each step that writes it given it at construction | #718, 411 lines, 31 files, accepted |
| 20 | `feat/health-rule-client-unreachable` | the health model's first pieces; aMule unanswering a rule | #756, 624 lines, 17 files, accepted |
| 30 | `feat/health-rule-channel-not-connected` | each channel's not connected rule | #721, 386 lines, 9 files |
| 40 | `feat/health-rule-channel-not-connectable` | each channel's not connectable rule, the old alert timers removed | #722, 233 lines, 13 files |
| 50 | `feat/health-rule-disk-space-low` | the disk's rule, its edge tracker removed | #741, 314 lines, 19 files |
| 90 | `docs/lot-4b1-wrap` | closing block | |

### Lot 4b2, the supervisor

| Block | Branch | Content | Draft, its size |
|---|---|---|---|
| 10 | `refactor/work-status-reading` | `Work`, `Supervisor`; the status reading the first work | #723, 276 lines, 18 files |
| 20 | `refactor/download-round-run-once` | the download cycle's round renamed `run_once` | #724, 91 lines, 7 files |
| 30 | `refactor/work-download-tracking` | download tracking a work, the download loop removed | #725, 449 lines, 10 files |
| 40 | `refactor/work-source-tracking` | source tracking a work of its own | #726, 446 lines, 11 files |
| 50 | `refactor/work-keyword-searches` | one work per client, channel and keyword | #727, 469 lines, 12 files |
| 60 | `refactor/supervisor-drives-works` | the supervisor running every work's turns | #728, 249 lines, 10 files |
| 90 | `docs/lot-4b2-wrap` | closing block | |

### Lot 4b3, a bug fails its turn alone

| Block | Branch | Content | Draft, its size |
|---|---|---|---|
| 10 | `feat/turn-ends-expected-or-bug` | `ExpectedError`; a bug fails its turn alone, 60 s before the next | #729, 454 lines, 29 files, accepted |
| 20 | `feat/search-errors-raised` | a failed search raised once its backoff is saved | #730, 63 lines, 5 files |
| 30 | `fix/amuleapi-request-total-bound` | a request to aMule bounded at 60 s | #733, 83 lines, 10 files |
| 40 | `feat/search-starts-kept` | each client's latest search starts kept in `local.db` | #734, 841 lines, 25 files, accepted |
| 50 | `feat/turn-time-limit` | each work's time limit; the notifications shielded | #735, 454 lines, 12 files, and #751's shield |
| 55 | `feat/notifications-shielded` | the notifications shielded (Corrected: split out of block 50, which with the shield came to about 570 lines and 21 files, the lead on 2026-11-16) | #751's shield |
| 90 | `docs/lot-4b3-wrap` | closing block | |

### Lot 4b4, the restarts of the aMule client

| Block | Branch | Content | Draft, its size |
|---|---|---|---|
| 10 | `feat/health-rule-bugs` | the bugs rule, recorded by the supervisor | #736, 424 lines, 19 files |
| 20 | `feat/health-rules-searches-and-network` | "searches failed", "connected to no network" | #737, 280 lines, 14 files |
| 30 | `refactor/client-works-built-together` | the works over the client built by one function | #739, 315 lines, 1 file (Corrected: 790 lines, 7 files, the moved code counted twice, accepted by the operator on 2026-11-17, "A") |
| 40 | `feat/client-rebuilt` | `Restartable`, `RestartPolicy`, the client rebuilt | #738, 1 198 lines, 21 files, accepted (Corrected: 1 427 lines, 30 files, `SupervisedWork`'s move, the holder, the core's two asyncio names and the tests written out) |
| 90 | `docs/lot-4b4-wrap` | closing block | |

### Lot 4b5, the webui and the notifier

| Block | Branch | Content | Draft, its size |
|---|---|---|---|
| 10 | `feat/webui-thread-watch` | the webui's thread watched every minute | #742, 222 lines, 14 files (Corrected: merged with block 20, 761 lines, 19 files, rather than carry code from one block to its user in the next, accepted by the operator on 2026-11-17, "reco ok, b") |
| 20 | `feat/webui-rebuilt` | the webui rebuilt | #743, 297 lines, 6 files (Corrected: merged into block 10) |
| 30 | `feat/notification-sends-recorded` | each send recorded on the notifier | #744, 364 lines, 16 files (Corrected: merged with block 40, 658 lines, 21 files, "reco ok, b"; past the file bound at 20 files, then at 21 with `parts_without_works` kept required, each accepted by the operator on 2026-11-17, "A") |
| 40 | `feat/notifier-rebuilt` | the notifier rebuilt | #745, 242 lines, 15 files (Corrected: merged into block 30) |
| 50 | `feat/notification-services-rules` | one component and one rule per service | #746, 497 lines, 19 files, and #754's contract (Corrected: written as one block, 604 lines and 21 files without the contract, it was cut into 50, the notifier listing its services and sending to one, 487 lines, 16 files, and 53, `feat/notification-service-parts`, one part per service and the contract, 292 lines, 18 files, accepted by the operator on 2026-11-17, "reco ok") |
| 80 | `fix/lot-4b5-review-fixes` | the holistic review's fixes in the code (Corrected: split out of block 90, which came to 382 lines and 27 files, the lead on 2026-11-17) | |
| 90 | `docs/lot-4b5-wrap` | closing block | |

## 6. Limits and scope

### Accepted limits

- **An intermittent bug, one that never strikes three turns in a row, never turns its rule failing nor writes a health
  line** (D5): its trace is in the log each time.
- **A repeating pattern of three detections in a row reads failing**, though the part still does half its work: three
  detections in a row cannot be told from an outage.
- **A bug that strikes every time on one keyword rebuilds its client up to three times**, losing the searches in flight
  each time.
- **No static proof of which errors are expected** (D9): the bug by default, the contracts and the release candidate's
  fault injection stand in for it. The test listing every port's expected errors is written by hand, so a new port's
  error is missed until someone adds it.
- **A notification is lost if the process dies between a decision's write and its send**, as today.
- **The rules start unknown after a restart of the crawler**, until they have enough checks.
- **While aMule is unreachable, the channels' rules keep their latest readings**: an unknown reading records nothing.
  A channel failing five readings, then unknown, then failing alerts at its next failed reading, where today it alerts
  five minutes later.
- **From lot 4b3 to lot 4c, a password refused while the node runs alerts nothing**: an expected error each turn, the
  searches failing, a line in the log.
- **A turn that grows past its limit's 5 minutes of margin is cut as a bug**: the download works grow with the tracked
  downloads and their sources, a search with the files of its answer, none bounded by a setting. A lost-media node
  tracks few downloads (the operator, 2026-11-11).
- **After three rebuilds in vain that succeeded, the object's works run on**, only the buggy turns failing, and the
  count resets once every bugs rule of its components is healthy again; after three rebuilds that raised, nothing of
  the object runs until the container restarts (the operator, 2026-11-12).
- **A timeout counts toward a notification service's rule as a refusal does** (the operator, 2026-11-12).
- **After a rebuild of the notifier, its count of rebuilds in vain resets only once every service has had 3 sends
  since the rebuild**, its bugs rule healthy again: a community service a lost-media node seldom notifies holds the
  count open, so later, unrelated bug episodes count in vain, and after three the notifier is not rebuilt again
  until then; it still sends. (Corrected: added by lot 4b5, the operator on 2026-11-17, "A".)
- **Source tracking's failed read waits a full `sources_interval`**, a fixed cadence (the operator, 2026-11-12).
- **During lot 4b2, a bug still stops the node, as today**, until lot 4b3; the supervisor's turn loop starts inside
  `Work` and moves into the supervisor at block 60.
- **No release ships between these lots**: v5 ships after lots 4c to 7 and their release candidates.

### Adjacent backlog items

- **v5 release readiness**: this spec implements its sub-entry 4b, deleted when lot 4b5 merges. Its wording ("health
  conditions on a graph of components") and that of the sub-entry 4c ("what the operator sees of health") name the
  lot 4 spec's words; lot 4b1's first commit corrects both to name this spec, the graph being lot 4c's.
- **Lot 5, the webui**: untouched; its `/health` row meets lot 4c, not this lot.
- **Multi network stage 5**: D13's rows are keyed by client, channel and scope for its clients too; nothing else of it
  is built; it stays open.
- **Contract tests for the fakes of outside systems**, **a generic way to write the tests' stubs and spies**, **test
  quality**, **mutation testing in the gate**: untouched; they stay open.

## Appendix A. Design

### Names

Each concept, what it is, and an example. The glossary gains each line in the block that brings the concept.

| Name | What it is | Example |
|---|---|---|
| `Component` | a part of the node whose health is tracked | the aMule client; Kad; the keyword "keroro" on Kad |
| `HealthRule` | one way a part can be unwell, with the thresholds that judge it | `CLIENT_UNREACHABLE`: failing once detected 3 times in a row, healthy again once detected fewer than 2 times in the last 10 |
| `Detections` | how many times a rule detected its case among its latest checks | 2 among the last 10 |
| `HealthState` | what a rule says of its part | unknown, healthy, failing |
| `HealthTransition` | a change of one part's state under one rule | `client amuled, unreachable: healthy to failing` |
| `NodeHealth` | the one place every check is recorded | `record(on=client, rule=CLIENT_UNREACHABLE, detected=True)` |
| `HealthAlerter` | sends today's alerts when a rule changes | "amuled unreachable for 2 min" |
| `Work` | a task the node repeats: a turn, then a wait before the next | the status reading, every minute |
| `Supervisor` | runs every work, bounds each turn, records how it ended | |
| `SupervisedWork` | a work, its time limit, and from lot 4b4 the components its turns are recorded on | |
| `ExpectedError` | an error the code expects from outside: aMule down, a search refused, a full disk; any other exception is a bug | `ClientError`, `StoreError` |
| `TurnTimeoutError` | a turn cut past its time limit, counted as a bug | |
| `Restartable` | an object holding state in memory that the node can rebuild | the aMule client, the webui, the notifier |
| `RestartPolicy` | decides when to rebuild an object, and stops after three rebuilds in vain | |
| `BackoffSaver` | sets the channels' backoff in its store after each search turn | |
| `LatestSearchStart` | when a client last started a search on a channel, for one scope | eD2k at 12:00:00 |
| `WebuiThreadWatch` | looks every minute whether the webui's thread still runs | |
| `NotificationRefusedError` | a notification service refused a send | a Discord 4xx |

`Component` offers what the restarts need besides `record`: `state(rule)`, a rule's current state, and `forget(rule)`,
which forgets a rule's latest checks so the rule is unknown again. `BackoffSaver` keeps its name: the glossary's
`record` and `set` name a `Writer`'s methods, and it is a step.

Names the first stack used and this spec drops: `Outcome`, `OutcomeSource`, `DeclaredFailure`, `Bug`, `Band`,
`AtLeast`, `Below`, `ConditionWindow`, `ComponentLabels`, `HealthCondition`, `Health`, `HealthRecorder`,
`HealthEventTranslator`, `ClientNotAnswering`, `UNITS_OF_WORK`, `TurnPastItsLimit`, `StateOwner`, `WebuiLiveness`,
`NotificationTimedOut`, `NotificationFailed`; and from #756, `FailureThreshold`, `record_failure`, `record_success`,
`counts`.

### The model, as the code reads

```python
# domain/health: pure, no I/O
CLIENT_UNREACHABLE = HealthRule(
    name="unreachable",
    fails_at=Detections(times=3, among_last=3),
    recovers_under=Detections(times=2, among_last=10),
)
client = Component(name="client amuled", client_name=ClientName("amuled"), rules=(CLIENT_UNREACHABLE,))

# application/steps: the status reading
try:
    status = await self._client.status()
except ClientAuthError:
    raise  # a wrong password is configuration, not an outage
except ClientError:
    status = None
await self._node_health.record(on=self._client_component, rule=CLIENT_UNREACHABLE, detected=status is None)
for channel in status.channels if status else ():
    kad_or_ed2k = self._channels[channel.channel]
    await self._node_health.record(on=kad_or_ed2k, rule=CHANNEL_NOT_CONNECTED, detected=not channel.connected)
    if channel.connectable is not None:  # a field aMule did not give records nothing
        await self._node_health.record(
            on=kad_or_ed2k, rule=CHANNEL_NOT_CONNECTABLE, detected=not channel.connectable
        )

# application/steps: the supervisor, once a turn has ended
bug = False
try:
    await self._within_time_limit(work)
except ExpectedError as error:  # aMule down is not a bug
    self._logger.warning("%s: %s", work, error)
except TurnTimeoutError:
    self._logger.error("%s: past its time limit of %g s", work, work.time_limit.total_seconds())
    bug = True
except Exception:  # the boundary of a turn, by design
    self._logger.exception("bug in %s", work)
    bug = True
for component in work.components:
    await self._node_health.record(on=component, rule=BUGS, detected=bug)
```

`NodeHealth` logs each change, then calls its subscribers in order: `HealthAlerter` (lot 4b1), then `RestartPolicy`
(lot 4b4); the order is fixed so the log reads the same at every run. A component carries what the alerts name it by,
as typed fields: its client, its channel, none where it has none.

### The rules

| Component | Rule | Fails at | Healthy again under | Recorded by | Lot |
|---|---|---|---|---|---|
| the aMule client | unreachable | 3 of 3 | 2 of 10 | the status reading | 4b1 |
| each channel | not connected | 6 of 6 | 2 of 10 | the status reading | 4b1 |
| each channel | not connectable | 6 of 6 | 2 of 10 | the status reading | 4b1 |
| download tracking | disk space low | 1 of 1 | 1 of 1 (the first good reading) | the download decision | 4b1 |
| the status reading, each keyword search, each channel, download tracking, source tracking | bugs | 3 of 3 | 2 of 10 | the supervisor, a search turn also on its channel | 4b4 |
| each channel | searches failed | 3 of 3 | 2 of 10 | each search turn | 4b4 |
| download tracking | connected to no network | 6 of 6 | 2 of 10 | the status reading | 4b4 |
| the webui | bugs | 3 of 3 | 2 of 10 | the supervisor, through its thread watch | 4b5 |
| each notification service | bugs; sends failed | 3 of 3 | 2 of 10 | the notification dispatcher | 4b5 |

The aMule client's own component carries no bugs rule: no turn is recorded on it, so the rule would stay unknown and
the count of D15 would never reset. The thresholds are constants of the code, tuned at the release candidate. The six
readings of the channels and of "no network" keep today's five minutes before an alert; the three of the client keep
today's two minutes. A rule's alert says how long it has held, derived where the rule is written: (readings needed - 1)
x the status period.

### Lot 4b1

- **Block 10** (draft #718): the composition resolves the node id right after the node id store opens, before the
  webui, and gives it at construction to each step that writes it; the steps that only passed it on lose it (the
  first stack's handoff, block 10, lists both); the lifecycle loses its resolution step. The stores keep the id where it is the value written or a key of catalog.db, which holds
  every node's rows. Past the file bound: a constructor argument across 31 files, nothing to split it by, accepted by
  the operator on 2026-11-11.
- **Block 20** (draft #756): `domain/health/` (`HealthRule`, `Detections`, `HealthState`, `HealthTransition`,
  `Component`) and its explanation in `__init__.py`; `NodeHealth` and `HealthAlerter` in `application/steps/`;
  `CLIENT_UNREACHABLE` replaces the status loop's API timer. #756 changes to D3's form, `record(on=..., rule=...,
  detected=...)`, no `counts` on the rule. `docs/contributing/architecture.md` gains its section on health. Past the
  line bound: the model's pieces cannot come without their first user, the operator's rule of 2026-11-11 ("On fusionne
  les paires de blocs").
- **Block 30** (draft #721): one component per channel, built by the composition once the client lists its channels;
  `CHANNEL_NOT_CONNECTED`, recorded from the reading's `connected` field; the channel's not connected timer removed.
  `docs/operate.md`'s sentence on an unknown reading corrected (#750).
- **Block 40** (draft #722): `CHANNEL_NOT_CONNECTABLE`, from the `connectable` field, which an unknown value leaves
  unrecorded; the old `_AlertTimer` removed with its last user.
- **Block 50** (draft #741): download tracking's component, built by the composition; `DISK_SPACE_LOW` recorded by the
  download decision at each free-space reading; `HealthAlerter` sends the disk alert, the floor given at its
  construction; `EdgeState` removed with its only user.
- **Block 90**: the handoff, the holistic review's fixes, the matching comparison.

### Lot 4b2

The supervisor's preparation, then its swap, behaviour unchanged but for block 40's two changes. Each work waits before
its turn, the first one included, its wait computed from its own state.

- **Block 10** (draft #723): `LoopSupervisor` renamed `Supervisor`; `Work`, an abstract class with `run_once()`,
  `wait_for_next_turn()` and, for now, a concrete `run()` (its wait, its turn, a yield, again); the status reading the
  first work, its wait a full period from the end of its latest reading, none at first; `architecture.md` updated.
- **Block 20** (draft #724): the download cycle's round renamed `run_once`, nothing else.
- **Block 30** (draft #725): download tracking (snapshot, tracker, decision, starter) a work, its wait none at first,
  then the poll or the wake; `DownloadLoop` removed.
- **Block 40** (draft #726): source tracking a work of its own, reading the client's list. Two changes, named in its
  pull request and in `docs/settings.md`: its turns run `sources_interval` apart from start to start, where today they
  wait the interval after each round; the start is stamped before the read, so a failed read waits a full interval.
- **Block 50** (draft #727): one work per client, channel and keyword, listed by the composition, its wait the
  channel's backoff, so a persisted backoff delays the first search after a start as today; `BackoffSaver`, shared by
  the search works, its snapshot taken at the first turn, the backoff set after each turn; `SearchTaskRunner` removed.
- **Block 60** (draft #728): the turn loop moves from `Work.run()` into the supervisor, `supervise(works)`, which arms
  the shutdown's bound and stops every work at the shutdown; a bug still ends the node.
- **Block 90**: the handoff, the holistic review's fixes, the matching comparison.

### Lot 4b3

- **Block 10** (draft #729): `ExpectedError`, every error a port declares derived from it, `ClientAuthError` among
  them; the supervisor's three ends of a turn (above), each logged in one line, a bug with its trace; 60 s at least
  before the next turn after a bug, the later of that and the work's own wait; the status reading lets a refused
  password through, source tracking its `StoreError`. `Work` and every test double name themselves for the log. Past
  the file bound: each port's error re-based is one line in each of its files, and splitting it from its first reader
  leaves a base class nobody reads, accepted by the operator on 2026-11-11 ("recos ok"). (Corrected: past the line
  bound too, 546 lines, accepted by the operator on 2026-11-16, "A": the three ways a turn ends cannot come without
  their acceptance tests.)
- **Block 20** (draft #730): the search raises `SearchFailedError` and `ClientUnreachableError` once its backoff and
  events are done, `BackoffSaver` setting the backoff in a `finally`, a cancelled turn included.
- **Block 30** (draft #733): the amuleapi adapter bounds a whole request at 60 s, its expiry a
  `ClientUnreachableError`, six times the 10 s of each phase; a page read within 60 s in all never meets it.
- **Block 40** (draft #734): `LatestSearchStart` (channel, scope, instant), the `SearchStartWriter` and
  `SearchStartReader` pair over `local.db`'s new table `latest_search_starts` (client name, channel, scope, instant in
  micros, the first three its key), its contract and fake. The adapter writes a start as it reserves it (eD2k under its
  lock, a Kad slot converted to the wall clock) and reads them once when it is built, each through `remaining_wait`. A
  `StoreError` is logged: on the read the client starts without them, on the write the search goes on. Past both
  bounds: no cut leaves each part with a production user, accepted by the operator on 2026-11-12 ("approuvé").
  (Corrected: 934 lines, past the 841 of its draft: its tests written out, four tests added.)
- **Block 50** (draft #735, and #751's shield): `SupervisedWork` (a work and its time limit); the turn raced against
  `MonotonicClock.sleep` in a task group whose expiry cancels the turn, a turn past it a `TurnTimeoutError` counted as a
  bug; the yield after a turn removed. Each limit is the sum of the bounds on its turn's path plus 5 minutes (`S` the
  60 s start spacing, `B` the 120 s search budget, `N` `notification_timeout_seconds`, `K` the keywords, `K_w` those
  sharing one Kad word, itself included, `c` one amuleapi call, its re-login included):
  - the status reading: `2c + (1 + 2·channels)·N`;
  - an eD2k search: `(K-1)·max(S, B+2c) + S + B + 3c`; a Kad search: `K_w·S + 2B + 4c`;
  - download tracking and source tracking: `2c + N` each;
  - the webui's watch: the margin alone.

  The sends after a decision's or a completion's write are shielded from the turn's cancellation (`asyncio.shield`,
  allowed in the core), the dispatcher holding the shielded task until its end. If the block passes a bound, the
  shield splits out as block 55.
- **Block 90**: the handoff, the holistic review's fixes, the matching comparison.

### Lot 4b4

- **Block 10** (draft #736): `BUGS`; one component for each work (the status reading, each keyword search, download
  tracking, source tracking), and each channel's bugs rule, which its search turns are recorded on too;
  `SupervisedWork` gains the components its turns are recorded on; the supervisor records each turn on them; the log
  line the first reader.
- **Block 20** (draft #737): a channel's "searches failed", each search turn recording detected for a
  `SearchFailedError`, not detected for a search that ran, nothing for an unreachable client or a refused password, so
  an aMule outage never heals the rule; download tracking's "connected to no network", recorded by the status reading,
  nothing on a node without `download:`, which has no download tracking.
- **Block 30** (draft #739, and #753's tests): the works over the aMule client built by one function of the
  composition, which the first build and every rebuild call; the download steps that hold no client built once;
  behaviour unchanged; the mapping of components to their objects and the works' functions tested as the node wires
  them. (Corrected: one class, `AmuleClientWorks`, whose `over(client)` is that function and whose constructor builds
  the parts once, `keyword_searches` taking each search's part from it, accepted by the lead on 2026-11-17; the
  mapping and its test came in the closing block, `amule_client_restart_policy` beside the class.)
  (Corrected: lot 4b5 block 10 replaced `amule_client_restart_policy` with
  `composition/node_restart_policy.py`, over the client, the webui and the notifier.)
- **Block 40** (draft #738, and #751's restart fixes, #752's holder): the `Restartable` port, its contract and fake;
  `RestartPolicy`, a subscriber of `NodeHealth`, handing the supervisor one `RestartRequest`; `Supervisor.add` for the
  rebuilt works. (Corrected: no public `Supervisor.add`: the policy hands the request to `Supervisor.restart`, which
  queues it for the supervisor's task of restarts, and the supervisor runs the works the object hands back itself;
  `Restartable` is generic in the works it hands back, `Restartable[W]`, since a port cannot import the steps, and
  `SupervisedWork` moved to `work.py`, so the policy and the supervisor import each other's names without a cycle.) The rebuild runs in a task of the supervisor, never in the turn that triggered it: the supervisor stops
  and awaits the object's works (Corrected: once, before the first attempt, not before each: a rebuild that raises
  hands no work back), the object rebuilds and hands its new works back, and only the bugs rules of its
  components are forgotten (forgetting a reading's rule would lose an open alert's end or send it twice). The aMule
  client's `Restartable`, in its own composition module, rebuilds every object holding the client; the composition
  names each component's object, a component without one refused at construction (Corrected: the refusal is the
  policy's, built over the map and the works: a part of two objects, a work recorded on no part or on a part of no
  object, brought back by the closing block; the map is derived from the works the client's first build hands
  back) (Corrected: since lot 4b5, from the first works of the client and the webui, and for the notifier from
  the parts the dispatcher records each send on, read from the dispatcher by `node_restart_policy`); the parts built before `NodeHealth` and the supervisor reach them through one holder, refusing a read before
  they are set (Corrected: the holder holds the restart policy alone, `RestartPolicyBuiltLater`: the policy is built
  after the works whose parts it maps, which record on `NodeHealth`; nothing reaches the supervisor before it is
  built, the works being handed back rather than added) (Corrected: since lot 4b5's closing block,
  one holder, `HealthSubscriberBuiltLater`, holds each subscriber built after `NodeHealth`: the alerts,
  whose dispatcher records each send on `NodeHealth`, and the restart policy). Rebuilds in vain counted, none
  past three, the count reset when every bugs rule of the object's components is healthy again; a rebuild that raises
  records detected on each bugs rule of the object's components and is tried again after 60 s; a login cancelled
  during a rebuild closes its httpx client (Corrected: brought into lot 4b3's closing block, the time limit cancelling a
  turn in its login there already). Past both bounds: the policy, the port and the client's rebuild cannot run
  apart, accepted by the operator on 2026-11-12 ("reco ok", "ça me semble ok").
- **Block 90**: the handoff, the holistic review's fixes, the matching comparison.

### Lot 4b5

- **Block 10** (draft #742): `WebuiThreadWatch`, a turn every minute over what the webui thread exposes (a callback
  the composition passes, the webui adapter depending on driving ports and the domain only); a dead thread is a bug of
  the webui's component. (Corrected: merged with block 20, "reco ok, b"; `composition/node_restart_policy.py`
  replaces `amule_client_restart_policy`, mapping each object to the parts its first works are recorded on, the
  notifier to the parts of its services through `parts_without_works`, which the closing block replaced by reading
  them from the dispatcher, with one debug line per object; the work named `webui` in the log, as its part, since
  the closing block.)
- **Block 20** (draft #743): the webui's `Restartable`, rebuilt by the composition; a rebuild whose port is held
  elsewhere does not raise, the watch fails it again, three rebuilds in vain. (Corrected: merged into block 10.)
- **Block 30** (draft #744): the dispatcher records each send on the notifier's component, after every send of the
  notification has ended: a send that worked records not detected on both rules; a `NotificationRefusedError` or a
  send past `N` seconds records detected on "sends failed" and not detected on bugs; any other exception records
  detected on bugs and nothing on "sends failed". (Corrected: merged with block 40, "reco ok, b"; each send on its
  service's part since block 53; a send whose notifier was rebuilt meanwhile is recorded on no part, since the
  closing block.)
- **Block 40** (draft #745): the notifier's `Restartable`, the dispatcher holding the rebuilt notifier through one
  indirection; a send in flight finishes on the old one. (Corrected: merged into block 30.)
- **Block 50** (draft #746, and #754's contract): the notifier lists its services and sends to one; one apprise object
  per URL; one component per service, named by its scheme and audience, never its URL, which carries a webhook's
  token; a URL apprise cannot load is a refusal logged at each send; `NotifierContract`, run by the apprise notifier
  and its fake. If the block passes a bound, the contract splits out as block 55. (Corrected: cut into 50, the
  services listed and sent to one by one, and 53, one part per service and the contract, "reco ok"; one bugs rule
  per service kept rather than one on a single notifier part, accepted by the operator on 2026-11-17, "A", with its
  limit in section 6.)
- **Block 90**: the handoff, `BACKLOG.md`'s sub-entry 4b deleted, the holistic review's fixes, the matching
  comparison.

### The first stack's closing fixes, where each goes

| Closing pull request | Where |
|---|---|
| #747, `UNITS_OF_WORK` | dropped: no rule names a source since D3 |
| #748, #749, the parts' names in the log | every block, by D17's last clause |
| #750, the review's small fixes | each in the block of the code it touches; the durations written `<seconds> s` everywhere; `operate.md`'s sentence in 4b1 block 30 |
| #751, the restarts' fixes and the shielded sends | 4b3 block 50 (the shield), 4b4 block 40 (the restarts) |
| #752, the holder of the parts built later | 4b4 block 40 |
| #753, the composition's works functions | 4b4 block 30 |
| #754, `NotifierContract` and the handoff | 4b5 block 50; each lot writes its own handoff |

### Settled at the first stack, kept

| Choice | Answer | Why |
|---|---|---|
| how a step knows the node id | at construction, the composition resolving it first | the operator, 2026-11-11 ("on uniformise avec les autres choses qui en avaient besoin") |
| code written in one block for a user in the next | merged into that block, past a bound if need be | the operator, 2026-11-11 ("On fusionne les paires de blocs") |
| what a change of health names | one rule of one component: the component, the rule, from, to | today's alerts are per field |
| what an unknown reading records | nothing | recorded as detected it would alert every channel, as not detected heal them |
| the wait and the first turn | the wait before every turn, the first included | a persisted backoff delays the first search, as today |
| the download split | two works, each reading the client's list | the operator, 2026-11-11: a skipped sources round would count as not detected |
| the order of lot 4b2 | prepare each work, then the swap, then the behaviour in lot 4b3 | the operator, 2026-11-11, so no two supervisors run side by side (Beck) |
| the backoff's snapshot | taken at the first turn | a snapshot before `resume_waits` would rewrite what it read |
| a password refused while running | an expected error, the node running, its rule lot 4c's | three rebuilds cannot repair a configuration |
| the latest starts' key | client, channel, scope | the operator, 2026-11-12: generic for other networks; "2 clients sur la même IP ... sont comptés différemment" |
| which task runs a rebuild | a task of the supervisor | the rebuild stops the works, the triggering turn among them (OTP) |
| a notification service's name | its scheme and audience | a URL carries the webhook's token |

### Pitfalls the first stack learned

Its handoff (`agents/handoffs/2026-11-12 - handoff - v5 lot 4b health model running.md`, on its closing branch
`docs/lot-4b-wrap`) lists them; each block's brief points at the section its block needs: Serena's renames, the core's
import rules (`asyncio.timeout` refused in the core, `TaskGroup` and `wait_for` allowed), the virtual-time loop's
traps, the composition's build order, recording inside and outside a turn, the nested recording of the notifier.

## Appendix B. Acceptance, in detail

| Row | Command, and the output that fails it |
|---|---|
| Client unreachable | a status loop test: three failed readings, then nine answers; fails if the alert is not sent at 120 s, if the end comes before or after the ninth answer, or if the log line is missing |
| Not connected, not connectable | status loop tests, a channel failing one field reading after reading; fails if its alert is not sent at the sixth reading or another field's alert is sent |
| Unknown reading | a status loop test: six failed readings, one unreachable, six failed; fails on an end or a second alert |
| Pattern | a rule test feeding `000111` twenty times, then ten checks not detected; fails on a state other than failing from the third detection to the end of the pattern, or a state other than failing before the ninth of the ten and healthy at it |
| Disk | a download decision test: two low readings, one above, two low; fails unless exactly two alerts are sent, neither with the free space |
| Lot 4b2 unchanged | each work's own tests; fails on a behaviour test of `main` removed rather than moved, the pull request listing each move |
| Source read | a source tracking test whose list read fails once; fails if the next read comes before a full `sources_interval` |
| Kad bug | the umbrella's probe `agents/reference/2026-11-04-v5-audit-instruments/fault-isolation/test_fault_isolation.py::test_a_kad_bug_stops_the_working_ed2k_tasks_too`, inverted and moved into the package's tests; fails if the eD2k searches stop (Corrected: rewritten over `Supervisor` and `keyword_searches` as `test_keyword_search.py::test_a_bug_on_every_kad_search_leaves_the_ed2k_searches_going_on`, the dated probe left as it is) |
| One keyword's bug | a supervisor test, two keywords, one raising at every search; fails if the other's searches stop |
| 60 s after a bug | a supervisor test whose work raises at once, its own wait 1 s; fails if two turns start closer than 60 s |
| Time limit | a supervisor test over `FakeBlockingMonotonicClock`, a work whose turn never returns; fails if no bug is recorded once its limit has passed (Corrected: over `FakeLoopMonotonicClock` on the virtual-time loop, since a blocking clock's sleep never ends and no limit could pass) |
| Ten eD2k keywords | `test_keyword_search.py`'s test of ten keywords queued on the real adapter's eD2k lock over `FakeAmuleApi`'s transport, each search held for its budget; fails on any bug |
| Password refused | a supervisor test whose client raises `ClientAuthError` at every call; fails if the node stops or a turn records a bug |
| Request bound | an adapter test on the real loop against a socket trickling its answer, the bound set under a second; fails if the call outlives its bound |
| Latest starts | adapter tests over a store holding a start 20 s old, then 70 s old; fail if the first start does not wait 40 s, or waits after the 70 s one; run for eD2k and for a Kad word shared by two keywords |
| Shielded sends | a test cutting a turn between a decision's write and its send; fails if the notification is not sent |
| Rebuilds | a restart policy test, a bugs rule failing with no recovery; fails unless exactly three rebuilds happen, then none |
| Raising rebuild | a restart policy test whose rebuild raises twice then succeeds; fails on a stop, on components not failing between the attempts, on two attempts closer than 60 s, or on works not running after the third |
| After three in vain | a test of three rebuilds in vain, then every bugs rule healthy, then a bug; fails unless the bug triggers a rebuild |
| aMule unreachable | a status loop and restart policy test; fails if anything is rebuilt |
| Rebuild under an alert | a restart policy test rebuilding the client while a channel's alert is open, then six failed readings; fails on a second alert or an end |
| Searches failed | a search work test, aMule refusing every search, then nine unreachable turns; fails if the rule does not turn failing, or if the unreachable turns change it |
| Webui | a test stopping the webui's thread; fails if the webui does not serve again after the rebuild |
| Notifier | a dispatcher test whose notifier raises a bug at every send; fails unless the notifier is rebuilt, three times in vain at most |
| Sends failed | a dispatcher test, one service refusing, another timing out; fails unless each service's rule turns failing |

## Appendix C. Facts

- The lot 4 spec's appendix C holds the measurements this lot rests on (the inventory, the cadence, the timings, the
  static tooling for exceptions, the sources), measured on 2026-11-09 at `629fdb03`.
- The first stack's sizes, by the workflow's command, each branch against its parent (2026-11-15): its 25 blocks total
  9 796 changed lines, 11 291 with the closing #747 to #754. Past a bound: #718 (411 lines, 31 files), #719 (738 lines,
  22 files), #729 (454 lines, 29 files), #734 (841 lines, 25 files), #738 (1 198 lines, 21 files). The sample #756,
  which replaces #719: 624 lines, 17 files.
- The first stack's CI was green on every pull request on 2026-11-13; its Docker integration suites mostly did not run,
  and no rebuild ran through the real composition on a node (its handoff, "Not validated").

## Appendix D. For lot 7

What the operator pages must say once lot 4b has merged; the first stack's handoff ("For lot 7") lists the log lines
in full.

- An alert's end held by the thresholds: "unreachable", "not connected" and "not connectable" end about nine readings
  after the recovery. An unknown reading keeps the channels' rules, so while aMule is unreachable no channel alert
  starts or ends.
- The disk alert without the free space.
- The new log lines: one per change of health; the supervisor's `bug in <work>`, `<work>: <error>` and `<work>: past
  its time limit of <seconds> s`; the restarts'; each notification service's refusals and timeouts; a failed search
  logged by the search and by the supervisor; source tracking's store failure logged by the supervisor; the latest
  starts store's two error lines; a dead webui's `bug in` line each minute; every duration written `<seconds> s`.
- Source tracking runs start to start.
- A password refused while the node runs no longer stops it.
- The new `local.db` table of the latest search starts; a node restarted within a minute of a search waits before that
  channel's next search.
- One rule for `docs/migration-4x.md` and the operator pages: a sentence a change makes false is corrected in the
  block that makes it false; new content is lot 7's.

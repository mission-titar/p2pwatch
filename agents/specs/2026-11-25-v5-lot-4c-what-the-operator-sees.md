# v5 lot 4c: what the operator sees of health

Tier Spec, lot 4c of `agents/specs/2026-11-04-v5-release-readiness.md`, built on lot 4b6's health model
(`agents/specs/2026-11-18-v5-lot-4b6-health-model-redrawn.md`). It replaces every lot 4c part of
`agents/specs/2026-11-09-v5-fault-isolation.md`. The decisions were settled with the operator on 2026-11-25 and
2026-11-26; the facts are measured at `840b4fbb` (appendix C).

## 1. In short

In v4 the crawler broke in silence: downloads never started, the node was never connectable, nobody was told. This lot
makes the alert the one thing the operator reads of health. An alert comes from a health rule, from a function that
stopped progressing, or from an object the supervisor could not repair; the notifications send it, the Node page lists
it while it is open, and `/health` fails while an object is unrepaired. Four fixes come with it: a watchdog for a
frozen crawler, one-line start refusals, a startup reevaluation that always reports, a rejected download notified.

## 2. What the operator will see

- An alert when the crawl of a channel or the downloads make no progress for 15 minutes.
- Every alert in two lines, what fails then what it costs, and an end when it is over.
- A notification service refusing our sends, alerted through the other operations services.
- Several alerts for one outage: amuled down sends its own, then a stall per function.
- The open alerts on the Node page.
- `docker ps` showing `unhealthy` while an object is left unrepaired.
- A frozen crawler restarted after 5 minutes, its stacks in the log.
- A database that cannot be opened refusing the start in one line that names its file.
- The startup reevaluation reporting what it did, skipped files included.
- A download amuled rejects, notified once.
- `p2pwatch_crawler_up` gone from `/metrics`.

Every exact text is in appendix D, for lot 7's operator pages.

## 3. Decisions

### The alerts

- **D35. The alert is the one concept: it opens and ends through the node's health, which keeps the open ones.**
  *One path, so the notifications, the Node page and `/health` show the same alerts.* Blocks 60, 70, 80.
- **D36. Every health rule has an alert and an end, which the type requires: `searches failed` gains its alert,
  `connected to no network` is removed, the disk's alert gains its end.** *A rule that only logs tells no one;
  `searches failed` alerts at 2 minutes where the stall waits 15, `connected to no network` repeats the channels'
  alerts.* Blocks 30, 40.
- **D37. A notification service refusing our sends is alerted through the other operations services.** *The failing
  service cannot carry its own alert; the others can.* Block 20.
- **D38. The crawl of each channel and the downloads of each client alert after 15 minutes without progress; a search
  answered empty is progress.** *A rule catches only the outages someone listed, a stall catches the rest; counting
  results alone would alert a node that finds nothing.* Blocks 90, 100.
- **D39. An alert's second line is a fixed text: what the outage costs, or where its cause may lie.** *The other open
  alerts and the log name the cause; nothing computes it.* Block 10.
- **D40. A download amuled rejects is notified once.** *The node never tries it again, and it may be an episode.*
  Block 150.

### What the operator reads

- **D41. The Node page lists the open alerts, each with since when.** *The operator sees what is wrong now without
  scrolling the notifications.* Blocks 70, 80, 85.
- **D42. `/health` answers 503 while an object is left unrepaired, 200 under any other alert; Docker reads it through
  `python -m p2pwatch health`, with a 30-minute start period.** *An unrepaired object is the one state a crawler
  restart may fix, and every outage has its alert; the start period covers a v4 catalog's first upgrade.* Blocks 70,
  110, 120.
- **D43. A watchdog stops the crawler when its event loop has not turned for 5 minutes, and Docker starts it again.**
  *A frozen loop is the one failure nothing on that loop can see, the alerts included.* Block 130.
- **D44. `p2pwatch_crawler_up` is removed.** *It is never set to 0, so it never told the truth.* Block 170.

### The start

- **D45. A database the crawler cannot open or migrate refuses the start in one line naming its file; the trace goes
  to the debug level.** *Today some 50 lines of traceback name no file.* Block 140.
- **D46. The startup reevaluation skips a file it fails on and goes on; a pass with skipped files runs again at the
  next start, and every pass ends with a notification.** *Today a bug on one file crashes every start, and a skipped
  file keeps a stale decision until the policy changes.* Block 160.
- **D47. The open alerts and the progress start from nothing at each start.** *A restart reads as a fresh start, and
  an outage still there alerts again.*

## 4. Acceptance

Each row's command and failing output: appendix B. The `rc` rows are checked on the operator's node at the release
candidate.

### The alerts

| Check | After the lot | On `main` |
|---|---|---|
| Kad's searches never complete for 15 min, every rule healthy | a stall alert, its end once a search completes | nothing |
| Every catalog write refused | a stall alert per channel | a log line per file |
| One file refused per search, the others recorded | no alert | a log line per search |
| Kad without contact, its searches answered empty | Kad's off-network alert, no stall | its alert |
| amuled unreachable for 15 min | its alert at 2 min, a stall per function at 15, each ending once amuled answers | its alert alone |
| The client rebuilt during a stall | no second alert | n/a |
| The download directory removed | the downloads' stall | a log line per round |
| A target complete, a candidate deferred for disk space | no alert | no alert |
| Today's alerts | a second line each | one line |
| The disk back above its floor | its alert's end | no end |
| eD2k refusing every search | its alert at the third refusal, its end | a log line |
| `connected to no network` | removed | a log line |
| A community service refusing every send | its alert through the operations service, its end | a log line |
| Two operations services, one refusing | its alert through the other | a log line |
| The one operations service refusing | no alert sent | a log line |
| A rule without an alert, an alert without an end | refused by mypy | accepted |
| rc: the longest gap between two searches per channel, over 24 h | under 7.5 min | n/a |

### What the operator reads

| Check | After the lot | On `main` |
|---|---|---|
| The Node page, amuled unreachable and Kad stalled | both alerts, since when | no alert shown |
| The Node page, an object left unrepaired | its alert | n/a |
| The Node page, no alert open | `No alert open` | n/a |
| `/health`, an object left unrepaired | 503, the object named | 200 |
| `/health`, other alerts open, or none | 200 | 200 |
| `python -m p2pwatch health` | exit 0 on 200, 1 otherwise or past 2 s | no such command |
| The event loop blocked past the watchdog's timeout | every thread's stack in the log, exit 1 | the crawler frozen |
| rc: the first start upgrading the v4 catalog | no watchdog exit | n/a |
| rc: `docker compose ps` once the node started | `healthy` | no healthcheck |
| `/metrics` | no `p2pwatch_crawler_up` | `p2pwatch_crawler_up 1` |

### The start

| Check | After the lot | On `main` |
|---|---|---|
| A catalog newer than the code | one line naming the file, exit 1 | a 44-line traceback |
| A catalog of random bytes | one line naming the file, exit 1 | a 55-line traceback |
| A bug on one file of the reevaluation | the others judged, the pass run again at the next start, the skip notified | every start crashes |
| A refused write on one file of the reevaluation | the same, without a trace | the pass marked done |
| The scan raising midway | the files left counted skipped, the start going on | every start crashes |
| The policy unchanged | a "not needed" notification | a log line |
| A pass completed | its counts notified | a log line |
| A download amuled rejects | notified once | a log line |

### What must not change

| Check | Observed by |
|---|---|
| The matching decisions on the real catalog | the umbrella's comparison: 0 differ |
| `deploy/matcher.yml` | unchanged, `validate-config` passing |
| The community notifications | their tests unchanged |
| The supervisor's rebuilds and the crawler's restart | lot 4b6's tests, their texts gaining only a second line |
| A healthy node | rc: no alert during an hour of searches |

## 5. Blocks

| Block | Branch | Content | Size |
|---|---|---|---|
| 10 | `feat/alert-second-line` | an alert's second line | ~320 lines, ~18 files |
| 20 | `feat/sends-failed-alert` | a service's refused sends alerted | ~235 lines, ~11 files |
| 30 | `feat/searches-failed-alert` | `searches failed` alerting, `connected to no network` removed | ~275 lines, ~13 files |
| 40 | `refactor/every-rule-alerts` | every rule alerting and ending, by type | ~270 lines, ~16 files |
| 50 | `refactor/node-health-test-builder` | the tests' `NodeHealth` built by one helper | ~70 lines, ~12 files |
| 60 | `refactor/alerts-open-and-end-through-node-health` | the node's health opening and ending every alert | ~290 lines, ~14 files |
| 70 | `feat/health-endpoint` | the open alerts published, `/health` | ~415 lines, ~19 files |
| 80 | `feat/open-alerts-on-node-page` | the open alerts on the Node page | 165 lines, 12 files (Corrected: measured) |
| 85 | `feat/open-alerts-since` | each open alert since when (Corrected: cut out of 80) | 149 lines, 19 files (measured) |
| 90 | `feat/crawl-stall-alert` | the crawl's stall | ~470 lines, ~19 files |
| 100 | `feat/downloads-stall-alert` | the downloads' stall | ~265 lines, ~12 files |
| 110 | `feat/health-command` | `python -m p2pwatch health` | ~350 lines, ~13 files |
| 120 | `feat/compose-healthcheck` | compose's healthcheck | ~75 lines, ~7 files |
| 130 | `feat/loop-watchdog` | the watchdog | ~240 lines, ~10 files |
| 140 | `fix/start-refusals-one-line` | one-line start refusals | ~165 lines, ~10 files |
| 150 | `feat/download-rejected-notification` | a rejected download notified | ~145 lines, ~8 files |
| 160 | `fix/reevaluation-per-file` | the reevaluation file by file | ~415 lines, ~11 files |
| 170 | `refactor/crawler-up-removed` | `p2pwatch_crawler_up` removed | ~100 lines, ~12 files |
| 180 | `docs/lot-4c-wrap` | closing block | |

One stack from `main`. Every rule alerts (10 to 40) before the node's health keeps the alerts (60), which `/health`
(70) and the Node page (80) read; the stalls and the healthcheck come next, the five independent pieces last. How the
sizes were measured: appendix C.

## 6. Limits and scope

### Accepted limits

- One outage can send several alerts, up to four for amuled unreachable.
- A stall is seen after 15 minutes.
- A stall is whole: one keyword failing while the other completes, or the source points refused, stall nothing; a bug
  of its own leaves the object unrepaired, with that alert.
- A channel answering every search empty while connected stalls nothing.
- With the deploy template's single operations service, that service's refusals alert no one.
- A notifier's work that stops taking turns, without a bug, alerts no one.
- A refused start notifies no one: the most the node can do without a watchdog outside it.
- No alert survives a restart, and a watchdog exit sends none.
- A frozen webui loop is caught by Docker's healthcheck alone.
- `/health` can wait behind a page's database read until lot 5.
- A bug in the reevaluation logs one line per skipped file, at each start until it is fixed.
- The reevaluation's first reads, before any file, still fail the start.

### Dropped

- The causes computed and grouped, and the Node page's report of functions, dependencies and objects: this spec's
  first version, overbuilt for what it brings.
- The draft's dependency graph, alert grouping, alerts persisted in `local.db`, three MicroProfile paths and health
  series in `/metrics`: no reader needs them.
- The catalog database as an external dependency, a rule for an inaccessible download directory, a fault test per
  port: a stall catches them.
- A refused start sent straight through apprise: it would read a configuration perhaps invalid, and send again at
  each restart.
- A reason for the start in "node online": the messages around it say enough.

### For lot 7 (umbrella D19)

Appendix D.

### Adjacent backlog items

- **v5 release readiness, its sub-entry lot 4c**: implemented here; block 10 names this spec in it, the closing block
  deletes it.
- **Lot 5, the webui**: its `/health` row stays its own; its retry button answers D40.
- **The in-memory stores without a fake**: the status reading's and the node metrics' fakes, debt under block 70's
  rule; the operator chose the backlog.
- **Lot 6, the release chain**: the rc rows need its release candidates.
- **The webui in the visitor's time zone**: the Node page's "since when" stays in UTC.
- **Multi network, stage 5**: the stalls will watch each new client's channels and downloads.
- **Contract tests for the fakes of outside systems**, **a generic way to write the tests' stubs and spies**, **test
  quality**, **mutation testing in the gate**: untouched.

## Appendix A. Design, block by block

Every piece sits in its ring: the alerts, the progress and the stalls are `domain/` and `application/steps/`, with no
I/O; what the webui reads is a Writer/Reader pair over our own state in memory, one adapter; the watchdog and the
healthcheck's HTTP client are adapters; the composition wires. Each block adds the glossary line of each concept it
introduces, and corrects the glossary lines, `architecture.md` and the docstrings it makes false.

### Names

| Name | Kind | Block | What it is |
|---|---|---|---|
| `detail` | field of `RelayedLogLine` | 10 | an alert's second line |
| `NotificationServiceSendsFailing`, `NotificationServiceSendsPassingAgain` | events | 20 | `sends failed`'s alert and its end |
| `SearchesRefused`, `SearchesAcceptedAgain` | events | 30 | `searches failed`'s alert and its end |
| `HealthAlert` | domain value, widened | 40 | an alert: its opening event, its end event (required), what it is about; sent by a rule, a stall or the supervisor |
| `open alert` | glossary word, `OpenAlert` from block 85 | 60 | an alert opened and not yet ended, with the wall-clock instant it opened from block 85 |
| `OpenAlertWriter`, `OpenAlertReader`, `InMemoryOpenAlertStore` | driven port pair, adapter | 70 | the alerts open, set by the node's health on the crawler's loop, read by the webui's thread |
| `watched function` | glossary word, `WatchedFunction` | 90 | a function as its progress is watched: the crawl on one channel of a client, the downloads on a client; never a `part`, which is an external dependency |
| `stall` | glossary word | 90 | a watched function that made no progress for `STALL_AFTER`; never a download making no progress, nor `lost`, D34's bugs verdict |
| `FunctionProgress` | application step | 90 | each watched function's latest progress on the monotonic clock, built once per client beside its dependencies |
| `StallWatch` | application step, a work | 90 | one per client, every minute: opens and ends the stall alerts of the client's watched functions through the node's health |
| `FunctionStalled`, `FunctionMovingAgain` | events | 90 | a stall's alert and its end |
| `HealthChecker`, `CheckHealth`, `HealthEndpointClient`, `UrllibHealthEndpointClient` | driving port, use case, driven port, adapter | 110 | `python -m p2pwatch health`, after `p2pwatch_amule`'s chain |
| `LoopWatchdog`, `FaulthandlerLoopWatchdog` | driven port, adapter | 130 | armed and disarmed by the crawler's lifecycle |
| `DownloadRejected` | event | 150 | D40's notification |
| `ReevaluationReported` | event | 160 | D46's notification, its three kinds |

A name a teammate derives from the Naming rules is the teammate's; this table fixes the concepts.

### Block 10, an alert's second line

- **Its first commit** carries this spec, the draft's mark (`agents/specs/2026-11-09-v5-fault-isolation.md`: lot 4c
  moved here), the backlog's sub-entry lot 4c corrected to name this spec, and under Debt its entry on the in-memory
  stores' fakes: "**The in-memory stores without a fake**: `FakeStatusReadingStore` and `FakeNodeMetricStore` removed,
  their tests using the stores themselves, a store in memory being its own double. Section 6 of
  `agents/specs/2026-11-25-v5-lot-4c-what-the-operator-sees.md`, its rule in `.claude/CLAUDE.md` from that lot's
  block 70."
- **`RelayedLogLine`** gains its second line, `detail`, none by default since most relayed lines have none (node
  online, the reevaluation's); apprise renders it on its own line; the policy's plan logs both lines joined with `: `,
  so the dispatcher is unchanged; the outbox's store reads an entry saved without it back with none, so no saved entry
  is dropped.
- **The second lines** of appendix D for today's alerts: unreachable, password refused, a channel off its network or
  not connectable, the disk, saves failed, the unrepaired object, the function lost.
- **Tests**: of the 15 test modules that build a `RelayedLogLine` (`git grep -ln RelayedLogLine -- tests`), the 9 that
  compare an alert change; the 6 others stay as they are, `detail` defaulting to none.
- **Why fixed texts**: the operator asked the cost on its own line, so as not to confuse the outage with what it
  costs; computing the cause was where the first version's complexity and errors lay (Kad answering empty while off
  its network).

### Block 20, a service's sends failed

- **`SENDS_FAILED`** gets its alert and its end, sent through every operations service but its own: the policy's plan
  names the service to skip, the dispatcher leaves it out of the audience's services (`NotificationOutbox.leave`
  already takes the services; no stored field changes).
- **A trap**: `events.py` cannot import `NotificationService` (`notification_sends.py` imports
  `external_dependency.py`, which imports `events.py`): the events carry the service's name as text.
- **Why**: lot 4b6 gave the rule no alert, its handoff saying it "must not go through the notifier"; the other services
  are not the failing one and can carry it, a community service failing being the case that matters. With no other
  operations service, the log and the Node page alone show it; a service refusing is still told at its third refused
  send, those three lost (lot 4b6's D30), and lot 4b6's limit "a notifier unrepaired on its operations service alerts
  no one" stands.

### Block 30, the client's and channels' rules

- **`SEARCHES_FAILED`** gets its alert and its end, `SearchesRefused` and `SearchesAcceptedAgain`, per channel; its
  glossary row loses "no alert names it".
- **Removed**: `CONNECTED_TO_NO_NETWORK` and its check in the status watcher, its glossary row.
- **Why**: `searches failed` fails at the third refusal in a row, about 2 minutes after the first, where the crawl
  stalls at 15; `connected to no network` fails on the same 6 readings as each channel's `not connected`, so at the same
  minute, and a client of one channel would say the same thing twice. A rule specific to an outage is kept when it
  alerts sooner than the stall (the operator, with more clients to come in v5).

### Block 40, every rule alerts

- **The type**: `ExternalDependency`'s `rules: Mapping[HealthRule, HealthAlert]`, `HealthAlert.when_healthy_again:
  Event`; mypy then refuses a rule with no alert and an alert with no end. The glossary's `health alert` row loses
  "or to `None`".
- **What an alert is about**: a text naming its part and rule (`client amuled, unreachable`), which block 60 keys the
  alerts open by; every `HealthAlert(` construction gives it (`git grep -n "HealthAlert(" -- src`, 5).
- **The disk's end**: `DiskSpaceSufficientAgain`, sent at the first reading at or above the floor.

### Block 50, the tests' `NodeHealth`

- **Mechanical**: a helper in `tests/support` builds the tests' `NodeHealth`, in place of its 14 constructions in 11
  test files (`git grep -n "NodeHealth(" -- packages/crawler/tests`), so block 70's new parameters touch one test file.

### Block 60, the alerts opened and ended through the node's health

- **`NodeHealth`** opens an alert (dispatches its opening, keeps it) and ends it (dispatches its end, drops it), keyed
  by what it is about. Opening an alert already open, or ending one not open, does nothing. `record` opens and ends
  its rules' alerts through them.
- **The supervisor** opens the unrepaired object's alert and ends it through `NodeHealth`, in place of its dispatcher,
  the object's name as what it is about.
- **The glossary's `open alert`**.

### Block 70, the alerts open published, `/health`

- **`NodeHealth`** takes an `OpenAlertWriter`, which it sets whole at each change: the alerts open, unstamped until
  block 85.
- **`InMemoryOpenAlertStore`** swaps a new tuple at each write, after `InMemoryStatusReadingStore`; its contract reads
  from another thread. No fake store: a store in memory is its own double (the operator), so the tests use it; the
  block records that rule in `.claude/CLAUDE.md`, the first to apply it.
- **The handler** reads the alerts open through its use case: `{"status": "UP" | "DOWN", "checks": [{"name": "client
  amuled", "status": "DOWN"}]}`, one check per object whose unrepaired alert is open, `DOWN` and 503 when one is.
- **Why**: the webui runs on its own thread, and a tuple swapped whole and never mutated needs no lock, as the status
  reading's store. MicroProfile Health's `/health` is the conjunction of every check, so one path follows it. An
  unrepaired object is the one lasting state a crawler restart may repair; a function lost restarts at once, and an
  outage has its alert (Kubernetes' liveness excludes the dependencies).

### Blocks 80 and 85, the Node page

(Corrected: block 80 measured 22 files once built, cut into 80, the alerts on the page, and 85, their instant.)

- **`DescribeNode`** (80) reads the alerts open beside `NodeStateReader`; `NodeDescription` gains them; `node.html`
  gains a section `Alerts`, each alert's two lines from the policy's plan of its opening event, and `No alert open`;
  its existing tests' `<td>` matchers kept exact; `architecture.md` describes the alerts open.
- **`NodeHealth`** (85) takes a `WallClock`, which stamps each alert it opens: an `OpenAlert`, the alert and the
  instant, which the store, `DescribeHealth` and the page then hold.

### Block 90, the crawl's stall

- **The crawl's progress**: `Cataloguer.catalog` returns whether the file was recorded (it returns the rows the file
  judge wrote today, 0 both for a file recorded with no decision changed and for a `StoreError` absorbed);
  `SearchWorker._record_observations` returns whether at least one reported file was recorded, or none was reported;
  `KeywordSearch.run_once` records progress on its channel in the client's `FunctionProgress` only then.
- **`FunctionProgress`** is built once per client by the composition beside the client's dependencies, so a rebuild of
  the client keeps it; it keeps the instant of the node's first watch turn, from which the 15 minutes count, not from a
  rebuilt object's.
- **`StallWatch`**, a work over the client, `function=None` like the status reading, every `STATUS_PERIOD`, its time
  limit `TIME_LIMIT_MARGIN` alone, as the webui's watch (`webui_restartable.py:33`), with no new method in
  `work_time_limits.py`: a watched function whose latest progress is older than
  `STALL_AFTER` (15 min) opens `FunctionStalled` through `NodeHealth`; one progressing again ends it.
- **Tests**: the rebuild row in `test_amule_client_works.py`.
- **Why a stall**: an alert on known outages fires only on what someone listed; one on the symptom fires whatever the
  cause, a swallowed error or a store refusing its writes included (the SRE book, appendix C). The notifications are
  watched per service by `sends failed` (block 20), not by a stall.
- **Why an empty answer is progress**: progress on results alone would alert a healthy node; v4's catalog holds 92
  gaps of more than 15 minutes with no observation of any keyword (appendix C). Kad without contact answers empty and
  has its own alert; Kad disabled and eD2k off its network refuse the search, which `searches failed` alerts.
- **Why 15 minutes**: above twice the backoff's longest wait (2 x 390 s), so a channel refused twice in a row does not
  alert, and far above a healthy channel's computed gap between two searches (under 2 minutes); the rc measures it.

### Block 100, the downloads' stall

- **The downloads' progress**: `DownloadCycle` records progress on the client's downloads in `FunctionProgress` once a
  round ends with every step done: the listing answered, the tracker's writes, the decider's measure and writes, the
  starter's. The tracker returns whether its writes passed, where it absorbs `StoreError` today
  (`download_tracker.py:58, 71, 80, 155`); the cycle knows the decider's and the starter's from its own `except`
  clauses (`download_cycle.py:138, 142, 152, 156`).
- **`StallWatch`** judges the downloads beside the crawl, on a node that downloads.
- **Wording**: `download_cycle.py:15, 102` ("a stalled download") reworded as a download making no progress;
  `architecture.md` describes both stalls.

### Blocks 110 and 120, the healthcheck

- **`python -m p2pwatch health`** (110): a subcommand over a driving port and its use case, a driven port and a urllib
  adapter reading `http://127.0.0.1:<webui port>/health` within 2 s, exit 0 on 200, 1 otherwise, as `p2pwatch_amule
  health` does.
- **`deploy/compose.yml`** (120): `healthcheck: test: ["CMD", "python", "-m", "p2pwatch", "health"]`, `interval: 30s`,
  `timeout: 3s`, `retries: 3`, `start_period: 30m` (above the first start's 10 minutes measured on the operator's
  catalog, appendix C), `start_interval: 30s`; the smoke compose follows, its dashboard probe
  (`test_compose_smoke.py:349-355`) staying the crawler's "started" signal in place of `p2pwatch_crawler_up 1.0`;
  `docs/contributing/architecture.md:999-1001` ("Le cœur n'a pas de healthcheck") corrected.
- **Why**: Docker does not restart an `unhealthy` container, so the state is for the operator's `docker ps`. A
  subcommand over a driving port, as the aMule container's healthcheck, keeps code out of compose. A check that
  succeeds ends the start period early, and the checks during it run every 30 s, so a 10-minute first start costs 20
  checks of 250 ms.

### Block 130, the watchdog

- **`LoopWatchdog`**, a driven port the crawler's lifecycle arms at the start of its run and disarms at its end, as it
  arms the shutdown's bound. **`FaulthandlerLoopWatchdog`** takes its timeout (300 s) and its beat (10 s) as
  parameters, the composition passing them: `faulthandler.dump_traceback_later(timeout, exit=True)`, re-armed at each
  beat by a `loop.call_later` chain, `cancel_dump_traceback_later` at the disarm. The loop's timer is not a clock read:
  the beat must run on the loop to prove it turns.
- **After the databases, by construction**: the composition opens both (`crawler_composition.py:411-417`) before it
  builds the lifecycle (`:624`), which alone arms the watchdog; the lifecycle's test proves it arms at its run's start,
  and the rc row on the operator's catalog the whole.
- **Tests**: a subprocess whose loop blocks on a `threading.Event` never set, past a short timeout, exits 1 with a
  stack on stderr; a loop that keeps turning past it does not.
- **Why**: a frozen loop is the one failure nothing on that loop can see, the supervisor included, while the webui's
  thread would go on answering. The beat is a callback of the loop itself, since no work turns during the
  reevaluation. Armed after the copy and the migrations, which hold the loop for minutes, so no upgrade is killed
  midway. 5 minutes is the time limits' margin, past which a work's turn is cut anyway; a beat every 10 s leaves 30 to
  the timeout. Its exit sends no alert, the notifier being frozen too: the operator sees "node online" again.

### Block 140, the start refusals

- **The database opener raises a domain error naming its file**, as `HeldDatabaseError` does, for a file it cannot
  open or migrate (today's `PersistenceError` and `MigrationError` at opening); the command line catches it and prints
  `Database refused, refusing to start: <reason> (<path>)`, the trace logged at debug. A `StoreError` met after the
  opening is not this refusal and goes on as today.
- **Why**: the log is stderr, where the line goes too; a refusal restarts under Docker anyway, one line says what to
  do, and the operator who needs the trace sets `log_level: DEBUG`.

### Block 150, a download rejected

- **`DownloadStarter`** takes the dispatcher and dispatches `DownloadRejected(file, filename, reason)`, an operations
  notification, beside its warning line; the file marked failed is never started again, so it sends once; lot 5's
  retry button answers it.

### Block 160, the reevaluation

- **`CatalogReevaluator`**: each file under its own `try`; `ExpectedError` skips the file with a line, any other
  exception with its trace for the first, a line for each next; a raise from the scan ends the pass, the files not
  reached counted as skipped; `ReevaluationSummary` gains `files_skipped`; the fingerprint stored only when it is 0;
  the pass dispatches `ReevaluationReported`; a pass the shutdown stops dispatches nothing. It takes the dispatcher.
- **Why**: today a bug on one file crashes every start, a crash loop that sends nothing since the notifier has not
  started. The scan's rows come from a generator that a raise finishes, so no later file can be read. The operator
  asked the "not needed" message too, so that each start says what it did.

### Block 170, `p2pwatch_crawler_up`

- **`NodeGauge.CRAWLER_UP`** and its setting in the policy removed. The 4.x Prometheus fixtures stay 4.x's output:
  their test compares to it less the removed series.

## Appendix B. Acceptance, in detail

| Row | Command, and the output that fails it |
|---|---|
| No search on Kad for 15 min | a `StallWatch` test on `FakeTime`, Kad's searches never completing; fails unless exactly one `FunctionStalled`, on one before 15 min of virtual time, or on a second line other than `cause: see the other alerts or the log` |
| A stall's end | the same, a search completing after the alert; fails on no `FunctionMovingAgain` |
| Every catalog write refused | a `KeywordSearch` and `StallWatch` test whose observation writer raises `StoreError`; fails if any progress is recorded or no alert follows |
| One file refused per search | the same, one file of each answer refused; fails on a `FunctionStalled` |
| Kad without contact | a status watcher and `StallWatch` test, Kad not connected, its fake searches answering empty as amuled does; fails on a `FunctionStalled` or on no `off its network` alert |
| amuled unreachable | the same, every reading and search unanswered; fails unless one unreachable alert at 2 min and one stall alert per watched function at 15 |
| The client rebuilt | `test_amule_client_works.py`, the client rebuilt while a stall alert is open; fails on a second `FunctionStalled` or on no end once a search completes |
| Directory removed | a `DownloadCycle` and `StallWatch` test with `InaccessiblePathError`; fails on no stall alert at 15 min |
| A target complete, a deferred candidate | the same, rounds completing with `SKIP_COMPLETE` and `SKIP_DISK_CAP` verdicts; fails on any alert |
| The disk's end | `test_download_decider.py`, the floor crossed back; fails on no end |
| Searches refused | `test_keyword_search.py`, the fake client raising `SearchFailedError` three times; fails on no `SearchesRefused` at the third, or on no end once a search passes |
| A community service refusing | a sender test, a community and an operations service; fails if the alert is not left for the operations one |
| Two operations services | a sender test, one refusing; fails if the alert is left for the refusing one, or not for the other |
| One operations service | the same, it alone, refusing; fails on any entry left |
| Second lines | `test_policy.py`, each alert of appendix D; fails on another text |
| The type | a test line declaring `{RULE: None}` under `# type: ignore[dict-item]`: mypy's `warn_unused_ignores` (strict) fails the gate the day the type accepts `None` again; the same for an alert with no end |
| `/health` | `test_app.py` over the use case and the in-memory store: an unrepaired alert open, then an outage's and a stall's alone, then none; fails on 200 for the first, on 503 for the others, on the object missing from `checks` |
| The Node page | a step-level test: `NodeHealth` over a real `InMemoryOpenAlertStore`, `DescribeNode` reading it, then `test_app.py`; fails if an alert is missing or its instant is not its opening's |
| Unrepaired on the page | a supervisor test after three rebuilds in vain, the store read; fails on no alert |
| `health` subcommand | a command-line test over a fake checker, then the urllib adapter's own test against a server slower than 2 s; fails on exit 0 for a 503 or past 2 s |
| Watchdog | a subprocess test as block 130's; fails if the process lives or stderr holds no `Thread` stack; the turning case fails on an exit |
| Watchdog after the databases | `test_crawler_lifecycle.py` over a fake watchdog, then the rc row: fails if it is armed outside the run, or on an exit during the upgrade |
| Start refusals | a subprocess `python -m p2pwatch crawl` on a catalog at `user_version 999`, then one of random bytes, its real stderr read; fails on more than one line or a line without the path |
| Reevaluation | `test_catalog_reevaluator.py`, one file raising `RuntimeError`, then `StoreError`, then a scan raising after two files, then the policy unchanged, then a complete pass; fails if another file is not judged, if the fingerprint is stored after a skip, if the pass raises, or on another text than the row's |
| A download rejected | `test_download_starter.py` over two rounds; fails on no `DownloadRejected` or on a second for the same file |
| `/metrics` | `git grep -n crawler_up -- packages/crawler/src` empty, a `/metrics` test; fails on the series present |
| rc: the longest gap | the completed-search log line per channel (`search_worker.py:123-129`) over 24 h of `docker compose logs p2pwatch`; fails at half of `STALL_AFTER` or more |
| rc: `healthy` | `docker compose ps` once "node online" is notified; fails on another state |

The umbrella's audit instrument expects `/health`'s old body
(`agents/reference/2026-11-04-v5-audit-instruments/fault-isolation/test_fault_isolation.py:293`); at the release
candidate it reads `{"status": "UP", "checks": []}`.

## Appendix C. Facts

Measured on `main` at `840b4fbb`, 2026-11-25, by the lead and three read-only inventory agents (`.reviews/v5-lot4c-
inventory-alerts.md`, `-webui.md`, `-faults.md`, gitignored); re-checked by the spec's reviewer on 2026-11-26.

### The rules today

| Dependency | Rule | Fails at / healthy under | Alert today |
|---|---|---|---|
| client amuled | unreachable | 3 of 3 / 2 of 10 | `amuled unreachable for 2 min`, end |
| client amuled | connected to no network | 6 of 6 / 2 of 10 | none |
| client amuled | password refused | 1 / 1 | `amuled refuses the password: check the configuration`, end |
| channel amuled ed2k, kad | not connected | 6 of 6 / 2 of 10 | `amuled kad: off its network for 5 min`, end |
| same | not connectable | 6 of 6 / 2 of 10 | `amuled kad: not connectable for 5 min`, end |
| same | searches failed | 3 of 3 / 2 of 10 | none |
| download disk | disk space low | 1 / 1 | `download disk low: under the 10.0 GiB floor (no new download)`, no end |
| local database | saves failed | 3 of 3 / 2 of 10 | `notifications not saved in local.db: lost at the next restart`, end |
| notifier service | sends failed | 3 of 3 / 2 of 10 | none |

- amuled accepts a Kad search while Kad runs without contact (amuleapi's `connecting`), and the search ends empty at
  Kad's 45 s lifetime (`src/SearchList.cpp:565`, `src/kademlia/kademlia/Defines.h:70` in the aMule tree the image
  builds from); it refuses a Kad search while Kad is not running (`disabled`, `SearchList.cpp:565-566`,
  `docs/api/REFERENCE.md:2564`) and an eD2k search while not connected (`SearchList.cpp:567`); the mapper reads
  anything but `connected` as not connected (`adapters/driven/amule_api/mapping.py:274-275`).
- A channel's connectable is known only while connected (`mapping.py:277`).

### Silent today

- `StoreError` caught and only logged: `cataloguer.py:76`, `catalog_reevaluator.py:92`, `download_cycle.py:138, 156`,
  `download_tracker.py:58, 71, 80, 155`, `source_watcher.py:131`, `backoff_saver.py:48`, and in the amuleapi adapter
  `amule_api_client.py:148, 273`; `InaccessiblePathError` at `download_cycle.py:142`.

### Cadence and windows

- Backoff: base 2 s, factor 2, cap 300 s, jitter 0.3 (`deploy/crawler.yml`): a channel refused at every search retries
  every 300 to 390 s.
- eD2k searches start 60 s apart at least (`START_SPACING`, `amule_api_client.py:77`); the status reading every minute
  (`STATUS_PERIOD`, `domain/status_reading.py:21`); a download round every 30 s (`deploy/crawler.yml`).
- Healthy cadence per channel, shipped config (2 keywords): eD2k 30 to 60 searches an hour, Kad 72 to 120
  (`agents/specs/2026-11-09-v5-fault-isolation.md`, appendix C), computed and never run on the node: the rc measures it.
- v4's catalog (read-only, `user_version 5`, 15 763 676 observations from 2026-07-04 to 2026-10-28, under v4's 300 s
  cycle): gaps of more than 15 minutes between two observations, 210 for `keroro`, 750 for `titar`, 92 for any
  keyword, of which 45 last 15 to 20 min, 19 last 20 to 30 min, 6 last 30 to 60 min, 6 last 1 to 6 h, 16 last 6 h or
  more. v4 records no channel and no empty search, and the long gaps hold the node's stops.
- `queue_new_candidates` skips a candidate without observation and one whose verdict is not `DOWNLOAD`:
  `SKIP_COMPLETE` for a target marked complete, forever, `SKIP_DISK_CAP` while the downloads in progress would take the
  disk under its floor (`download_decider.py:85-107`, `domain/download/policy.py:52-57`): neither is a stall, since
  its round completes.
- Every work over the client is built anew at each rebuild (`composition/amule_client_works.py:214`); the
  dependencies are built once (`:207-212`).
- The first start on the operator's catalog: the copy 380 s, migration 0007 225 s (umbrella appendix B, 2026-11-04);
  the webui starts after both (`crawler_composition.py:412-417, 525`).

### The webui and the watchdog

- The webui serves on its own thread and loop (`uvicorn_server_thread.py:65`); `InMemoryStatusReadingStore` swaps a new
  mapping at each write, read without a lock from the other thread (`in_memory_status_reading_store.py:24-28`).
- The image holds Python and no curl or wget (`packages/crawler/Dockerfile`); a healthcheck through `python -m
  p2pwatch` costs 250 to 360 ms and 61 MB, urllib alone 21 to 24 ms (dev machine, three runs each).
- `faulthandler` is imported nowhere; probed: a second `dump_traceback_later` replaces the first, `exit=True` writes
  every thread's stack then exits 1, a re-arm costs about 14 µs. The reevaluation runs after `build_first` and before
  `supervise()`, yielding the loop before each file (`catalog_reevaluator.py:77`).

### The start and the reevaluation

- A catalog at `user_version 999`: a 44-line traceback ending `MigrationError: db at version 999, code at version 15:
  db newer than the code, refusing to start (spec §3)`; a catalog of random bytes, 55 lines ending `PersistenceError:
  file is not a database` (the faults inventory, `uv run python -m p2pwatch crawl` in its scratch); neither names the
  file (`sqlite_database_opener.py:264-268`), and the command line catches neither (`argparse_command_line.py:141-170`).
- The log is a `StreamHandler` on stderr (`argparse_command_line.py:44-51`), where the refusals are printed too.
- A bug in `FileJudge.rejudge` is not caught (`catalog_reevaluator.py:92` catches `StoreError` alone), and no sender
  runs during the pass: a crash loop that sends nothing. The scan's rows are read and mapped inside its generator
  (`catalog_reevaluator.py:75`, `observation_read.py:121-123`).
- A skipped file is counted as judged and stores the fingerprint
  (`test_catalog_reevaluator.py::test_store_error_on_one_row_is_absorbed_and_sweep_continues`).
- A rejected download is marked failed and never started again (`download_starter.py:41-46, 59-67`).

### Sources

| Claim | Source |
|---|---|
| Alert on symptoms, not causes | Google SRE book, "Monitoring Distributed Systems", https://sre.google/sre-book/monitoring-distributed-systems/ |
| "Pages should be urgent, important, actionable, and real" | Rob Ewaschuk, "My Philosophy on Alerting", https://docs.google.com/document/d/199PqyG3UsyXlwieHaqbGiWVa8eMWi8zzAn0YfcApr8Q |
| MicroProfile Health's `/health`, its conjunction, 200 and 503, `status` and `checks`, an empty set `UP` | https://download.eclipse.org/microprofile/microprofile-health-4.0/microprofile-health-spec-4.0.html |
| Liveness independent of dependencies | https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/ |
| A healthcheck's start period: failures not counted, ended by a first success, checks at `start_interval` during it; Docker restarts no `unhealthy` container (no explicit sentence in its docs: the restart policy reads the exit) | https://docs.docker.com/reference/dockerfile/#healthcheck |
| `faulthandler.dump_traceback_later` | https://docs.python.org/3.13/library/faulthandler.html |

### Estimates

`lot4c-estimate-2` (Sonnet, 2026-11-26, `.reviews/v5-lot4c-estimate-2.md`, gitignored), from `git grep -l` on the
tree, then the spec's reviewer's recounts and the agent's third estimate over the re-cut blocks; plus or minus 25 %.
Blocks 10, 70 and 90 came at 22, 23 and 21 files, each brought under the bound: in 10, `detail` defaults to none, so
only the 9 test modules that compare an alert change; in 70, the glossary's `open alert` goes in 60, the `OpenAlert`
value in 85 and `architecture.md` in 80, and no fake store is written (the fourth estimate counted 70 at 22 with them: 19
without); in 90, the rebuild row is tested in `test_amule_client_works.py`, the watch's time limit needs no new method,
and `download_cycle.py`'s rewording and `architecture.md` go in 100.

## Appendix D. For lot 7, and every text

### The alerts

Each is an operations notification; the log line joins its two lines with `: `.

| Alert | First line | Second line | End |
|---|---|---|---|
| unreachable | `amuled unreachable for 2 min` | `impact: no search, no download` | `amuled reachable again` |
| password refused | `amuled refuses the password: check the configuration` | `impact: no search, no download` | `amuled accepts the password again` |
| off its network | `amuled kad: off its network for 5 min` | `impact: no search on kad, fewer sources for our downloads` | `amuled kad: back on its network` |
| not connectable | `amuled kad: not connectable for 5 min` | `impact: fewer sources can reach our downloads` | `amuled kad: connectable again` |
| searches failed | `amuled ed2k: the network refuses our searches` | `impact: no search on ed2k` | `amuled ed2k: the network accepts our searches again` |
| disk low | `download disk low: under the 10.0 GiB floor` | `impact: no new download` | `download disk above its floor again` |
| saves failed | `notifications not saved in local.db` | `impact: lost at the next restart` | `notifications saved again` |
| sends failed | `discord community refuses our notifications` | `impact: the notifications sent to it are lost` | `discord community accepts our notifications again` |
| crawl stalled | `search stalled on amuled kad for 15 min` | `cause: see the other alerts or the log` | `search on amuled kad moving again` |
| downloads stalled | `downloads stalled on amuled for 15 min` | `cause: see the other alerts or the log` | `downloads on amuled moving again` |
| unrepaired | `client amuled: search 'keroro' amuled ed2k still failing after 3 rebuilds` | `cause: a bug of its own, or a shared state a crawler restart would renew` | `client amuled: every work healthy again` |

A function lost is no alert left open: `the crawl lost: every search failing after 3 rebuilds`, `impact: the crawler
restarts`, then the crawler exits and "node online" follows.

### The other notifications

- `Reevaluation: not needed, policy unchanged`; `Reevaluation: 2162 files judged, 29 decisions changed`; `Reevaluation:
  2159 of 2162 files judged, 29 decisions changed, 3 skipped (their decisions may be stale)`, a scan that raised
  counting the files it did not reach as skipped.
- `download rejected by amuled: <filename> (<reason>)`.

### For the operator pages

- Every alert in two lines, each with its end; the disk's end; the stall alerts; a service's refusals alerting the
  other operations services; a channel's searches refused alerted; `connected to no network` gone from the log.
- The Node page's alerts open; `/health`'s new shape and 503; compose's healthcheck and `docker ps`'s `unhealthy`;
  `python -m p2pwatch health`; `docs/troubleshooting.md:83` ("Le crawler n'a pas de healthcheck") rewritten.
- The watchdog's exit and where its stacks are; "node online" after it.
- The start's one-line refusals naming the file, the trace at debug; the reevaluation's three notifications and a pass
  run again after a skipped file; a download rejected.
- `p2pwatch_crawler_up` removed, in the migration guide.
- "node online" reads as a fresh start: no alert survives a restart.

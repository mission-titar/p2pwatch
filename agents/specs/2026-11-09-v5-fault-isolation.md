# v5 lot 4: fault isolation

Tier Spec. Discussed with the operator on 2026-11-09, as lot 4 of `agents/specs/2026-11-04-v5-release-readiness.md`
(the umbrella), whose decisions D12 and D13 it implements; its findings are the umbrella's appendix A "Lot 4". The
decisions are the operator's; their reasons are those given in the discussion, the lead's included where the operator
accepted a recommendation. Every measurement was re-run on 2026-11-09 on `main` at `629fdb03` (appendix C). The lot is
cut in three lots merged one after the other, 4a, 4b and 4c (D21), each with its own stack, holistic review and
handoff, under this one spec. The spec's commit marks lot 1's spec, `agents/specs/2026-11-04-v5-amule-container.md`,
at its limits "A port-sync bug restarts amuled too" and "A `ListenPortError` that repeats" (`(Corrected: fixed by v5
lot 4's D20, every port-sync error logged and retried at the next poll)`), and commits the inventory's added probes
under `agents/reference/2026-11-09-v5-lot4-instruments/`.

## 1. In short

Today every loop of the crawler runs in one task group with no restart: an unexpected error anywhere (a bug on the
Kad channel, a failing metric write, a refused password) stops the whole node, webui included, and Docker restarts it
into the same error when its cause is persisted. `/health` always answers ok, and a crash loop reads as repeated
"node online" notifications. The lot gives the crawler a small internal health library, built on what the reference
practice settled (OTP supervision, Kubernetes conditions, resilience4j's windows, Alertmanager's grouping, MicroProfile
Health): every part of the node becomes a component of one acyclic graph, judged by conditions over its own outcomes;
a bug fails one search, the owner of a corrupted state is restarted, and an alert names each root cause once with what
it breaks. The crawler exits only when it cannot build that graph. On the way, the lot fixes the defects the inventory
found around it.

## 2. What the operator will see

- **A bug in one part no longer stops the node**: a bug on one keyword's search fails that search alone; a bug on one
  channel leaves the other channel searching and the downloads running.
- **One alert per root cause, saying what it breaks**: "aMule client unreachable; impact: search and download
  failing". Alerts opened together arrive in one message. The current connectivity and disk alerts become these.
- **An alert that repeats nothing**: an open alert survives a restart without being sent again, "node online" lists
  the alerts still open, and an alert's end is sent when its cause clears, even if it cleared while the node was
  stopped.
- **The Node page shows every component's health**, with its reason.
- **`/metrics` carries every component's health and its outcomes by reason**, enough to rebuild the same alerting in
  Alertmanager or Grafana; `p2pwatch_crawler_up`, never true, is removed.
- **The health endpoints tell the truth**, along MicroProfile Health's paths: started, live, ready; the old
  `/health`, which always answered ok, is removed. Compose gives `p2pwatch` a healthcheck on "live".
- **A refused aMule password no longer crash-loops the node**: the client shows failing with that reason, the webui
  stays up. A failed migration or an unreadable database refuses the start in one line, never a traceback.
- **A frozen crawler restarts by itself**, after writing where it froze to its log.
- **The crawl pause is gone**: the dashboard keeps its restart button only.
- **The port-sync never restarts the `ed2k` container for an error of its own**: it logs it and retries at its next
  poll.
- **`docker compose stop` is honoured during the first start's long steps**, and the shutdown is bounded.
- The operator pages are lot 7's (umbrella D19); section 6 lists what they must say.

## 3. Decisions

### The unit and its supervision

- **D1. The unit that fails is one search, a keyword on a channel, with a health of its own; a channel is judged from
  its searches and its own conditions; only the owner of an in-memory state is ever restarted.** *A search owns no
  state: the channel's pacing, its backoff and the aMule session belong to the client or to a shared, persisted
  registry, so a search is a temporary worker in OTP's sense, never restarted, and its failure costs that search
  alone. A restart can only repair what it rebuilds, so restarting a channel, which owns nothing, would repair
  nothing.* Lot 4b.
- **D2. A keyword whose search fails is searched again at its next turn like the others, and a bug never touches the
  channel's backoff.** *The node exists to miss nothing; a failure takes no capacity from the other keywords, which
  keep their turns; the backoff measures the network's refusals, and counting our bugs in it would slow every keyword
  for one keyword's bug.* Lot 4b.
- **D3. Every failure a driven port declares derives from one base type, and a failed outcome carries its reason:
  that failure's name, or `Bug` for anything else (an exception outside every contract, a unit of work past its
  maximum duration).** *Only the restart depends on the reason, and it only asks "is it a bug"; one base type lets the
  supervisor classify by the type alone, so a step goes on succeeding or letting a declared failure through, as
  today, and an undeclared exception is a bug by construction.* Lot 4b.
- **D4. The supervisor bounds each turn of a work by a maximum duration, set for each work; a turn past it is cancelled
  and becomes a `Bug` outcome.** *Nygard's Timeouts pattern; it turns a stuck task or a mute sensor into an ordinary
  failure, with more information than a heartbeat (which unit, stuck since when), and needs no separate silence
  rule.* Lot 4b.
- **D5. A bug repeated on a component restarts what holds its in-memory state (the client, the webui, the
  notifier), at most three times in vain; the composition restarts it by building it anew.** *A restart can only clear
  memory: a session, a lock, a cache, a thread; Gray found most production faults pass when the work is re-executed.
  An object built anew is fresh by construction, where a reset in place drifts with each attribute added; and an
  object's lifetime is its composition root's business (Seemann and van Deursen), so no factory leaves it. A failure a port declares (the network, aMule,
  the disk) is not repaired by a restart, which only worsens a cascade (Kubernetes, the SRE book).* The rules,
  appendix A. Lot 4b.
- **D6. Declared failures are guaranteed by behaviour, not by declaration: any exception outside the base type is a
  `Bug`; each adapter converts only the exception families it can name, never `Exception` wholesale; each port's
  contract tests provoke the real failures of its outside system; the leaks the inventory found are fixed in the lot;
  the release candidate injects faults on the node.** *No static tool proves which exceptions a library call raises
  (appendix C), and a declaration, a docstring section or a decorator listing families, can lie and drift. The
  default errs on the safe side: a leaked declared failure costs a few cheap restarts and an alert with its trace,
  which reveals the adapter's broken contract; the reverse, a bug taken for a declared failure, would hide it.* Lot
  4a, the base type in 4b.

### The health library

- **D7. One health model for every cause, kept and evaluated in the crawler, and exported in `/metrics`; the backoff
  stays a pacing mechanism apart.** *The connectivity alerts and the bug alerts say the same thing, "this part has
  been unwell for a while", for two causes; the supervisor must count failures in the process anyway to restart a
  state owner, which settles where the model lives; Prometheus and Alertmanager stay possible on the exported
  state.* Lot 4b, its surfaces lot 4c.
- **D8. The concepts and their names: `Component`, `Outcome`, `DeclaredFailure`, `HealthCondition`, `Health`
  (unknown, healthy, degraded, failing), `HealthTransition`, `HealthAlert`, `HealthGraph`, `Dependency` with its
  `Quorum`, `Supervisor`, `RestartPolicy`, `StateOwner`, and `Work`, what the supervisor runs again and again, one
  turn a call to `run_once()`.** *Each concept is taken from a reference that settled it (Spring, resilience4j, Kubernetes,
  Alertmanager, OTP, reliability block diagrams); a generic word another concept already uses is qualified on both
  sides: the matcher's `Condition` becomes `TokenExpression`.* Lot 4b, the rename in lot 4a.
- **D9. A condition counts failures among a component's last outcomes, with one threshold to enter a state and a
  stricter one to leave it.** *A count measures each component at its own pace, where a time window would leave a
  rarely used one unknown forever; two thresholds stop a periodic pattern from flapping. A single failure stays a
  log line.* The values, appendix A. Lot 4b.
- **D10. Every supervised component, each search included, carries a bugs condition counting `Bug` outcomes only; its
  other conditions count their own reasons, and a success counts for all.** *The restart policy reads that condition
  alone, so a part failing for mixed reasons is never restarted for a network outage, and always for a bug.* Lot 4b.
- **D11. One acyclic graph with one relation, "depends on", and a quorum per dependency (all, at least one, none): a
  component is failing when a quorum is not met, degraded when a dependency is degraded or failing; an unknown
  dependency degrades nothing.** *Fault trees and reliability block diagrams express series and parallel parts with one
  k-out-of-n structure, where a tree with clients and sensors set beside it was two mechanisms; a component receives
  its dependencies already built, so a cycle cannot be written; an unknown dependency degrading its parent would read
  the whole node degraded at every start.* The graph follows the node's roles, search and download, not its programs,
  so BitTorrent's two programs will fit it; the clients, the status sensor, the webui, the notifier and the databases
  are components like the others (appendix A). Lot 4b.

### What the operator sees

- **D12. One alert per root cause, a condition holding on a component, carrying its impact (the components it
  degrades or fails, up to the crawler); a component failing only through its dependencies never alerts; alerts
  opened together are sent as one message after a short wait.** *In a graph, "the highest failing level" is not
  defined, one cause reaching the top by two paths; Icinga suppresses a child's notifications behind a failed parent,
  and Alertmanager groups alerts of one nature into one notification.* Lot 4c.
- **D13. The open alerts are persisted in `local.db`, never announced again at a restart, listed in "node online",
  ended when their condition clears, closed at the start when their component no longer exists; the windows and the
  restart counts are not persisted.** *An alert is then never sent twice and its end is sent even when the cause
  cleared during a stop; restored outcomes would describe the world before a long stop, while "unknown" lasts only
  until a window fills; an alert on a keyword or a client removed from the configuration would otherwise stay open
  forever.* Lot 4c.
- **D14. HTTP health follows MicroProfile Health: `/health/started`, `/health/live` and `/health/ready`; compose's
  healthcheck reads live only; the old `/health` is removed.** *"Alive" can be repaired by a restart, "ready" depends on
  the network, which a restart cannot repair (Kubernetes, Spring): a tool restarting on `unhealthy` must never restart
  the crawler for a VPN outage. No tool the docs name reads a single URL, and the conjunction is easy to add when one
  does.* Lot 4c.
- **D15. A frozen event loop is caught by Python's own fault handler, armed once the graph runs and re-armed at each
  beat of the loop: past its timeout it writes every thread's stack and exits 1, and Docker restarts the crawler.**
  *It is the one failure the graph cannot see, running on that loop; the watchdog is the interpreter's own thread in
  C, so the chain of watchers ends: the loop, the interpreter, then Docker, outside the process; SQLite in WAL keeps a
  transaction whole or absent after a hard exit. The first start's copy and migrations hold the loop for minutes:
  armed before them, the watchdog would kill every upgrade midway, and each restart would start it over.* Its timeout
  stays well above the longest stretch measured (appendix C). Lot 4c.
- **D16. `p2pwatch_crawler_up` is removed, the crawler component's health series standing for it.** *It is set to 1
  at the start and never to 0, so it never told the truth; Prometheus's own `up` already says whether the node
  answers, and the health series says how it is.* Lot 4c.

### The real stops

- **D17. The crawler stops only when it cannot build its graph (the configuration, the databases' opening and
  migrations) or when the supervisor itself fails, in one line saying what to do; a refused password becomes a
  condition of the client, and the databases components whose writes feed a condition.** *Armstrong: the part that
  must be correct for the rest to fail safely; a refused password or an unwritable database is not repaired by a
  restart, so a stop only loops, while a condition keeps the webui and the alert up.* Lot 4c.
- **D18. The startup reevaluation judges each file under its own `try`; the pass is complete only when every file
  succeeded, else its fingerprint is not written, the whole pass runs again at the next start, and a condition counts
  the failed files.** *A bug of the engine is deterministic, so only a new release repairs it, and a release does not
  change the fingerprint; a pass of a few seconds makes replaying it cheap (appendix C). It fixes a latent bug: a
  storage error skipped its file and the fingerprint was written anyway, leaving that file's decisions stale until a
  search saw it again. No precaution is taken for a transient database error: both databases are in WAL with one
  writer, so no lock can occur, and a full disk is persistent.* Lot 4c.

### Around the model

- **D19. The crawl pause is removed: its two buttons, its two routes, its use cases and the pause half of the run
  state; the restart button stays.** *The operator does not use it and it is foreign to a crawler; it stopped searches
  only and was lost at every restart; without it, the health model has no exception for an intended silence.* Lot 4a.
- **D20. Five defects found by the inventory are fixed in the lot, each a failure that stops or misleads the node.**
  Lot 4a.
  - **The retry delay recognises its cap without computing past it, and `factor` and `jitter_ratio` get upper
    bounds.** *Umbrella D13: after about three days of refusals the delay overflows and stops the crawler, at every
    restart since the count is persisted.*
  - **A file's decisions are prepared in full, written in one transaction, then dispatched.** *A failed write then
    writes nothing and the next judgement redoes it all, notification included; an outbox that never loses a
    notification would be a feature of its own, not taken.*
  - **The shutdown is bounded: a signal during the opening, the migrations and the reevaluation is honoured promptly,
    compose's stop grace sits above the crawler's deadline, the close after the deadline is bounded, exit 0 is kept
    for a requested shutdown.** *Today a stop during the first start waits for the end of a ten-minute step, Docker's
    grace equals the deadline, and any timeout outside the loops reads as a clean stop.*
  - **Each round of the port-sync is a unit of work: any error, a bug included, is logged with its trace and retried
    at the next poll; the container exits only on an invalid setting at boot or the process's death.** *Lot 1 handed
    it to this lot: a refused login, a renamed route or a malformed body makes the port-sync exit today, restarting
    amuled with it about once a minute, which repairs nothing; the crawler's "connectable" condition shows a port not
    applied, the port-sync's log gives the cause.*
- **D21. The lot is cut in three lots merged in order, under this spec: 4a the ground and the independent defects, 4b
  the health model running, 4c what the operator sees and the real stops.** *Measured, the lot holds more than twice
  the 19 blocks a lot may hold (appendix C); 4a's blocks stand alone and prepare 4b (no pause to handle, no leak taken
  for a bug); at the end of 4b the model runs and the current alerts are produced by its conditions, the only change
  the operator sees being an alert's end, now held by the hysteresis; 4c replaces the surfaces.*

## 4. Acceptance

Commands for each row: appendix B. The rc row is checked on the operator's node at the release candidate.

### Lot 4a

| Check | After the lot | On `main` |
|---|---|---|
| The 1025th consecutive failure of a channel | the delay at its cap | `OverflowError`, the crawler stops |
| A `factor` of 11 or a `jitter_ratio` of 1.5 in `crawler.yml` | each refused by `validate-config` | accepted |
| The crawl pause | no route, no button | `/controls/pause` answers 303 |
| A failed write on a file's second decision | no decision of the file written; the next judgement writes and notifies them | the first decision written, its notification lost |
| A port-sync round raising (a 401 or 404 at login, malformed preferences, a bug) | logged, retried at the next poll, `ed2k` stays up | the port-sync exits, the container restarts |
| A SIGTERM during a migration or a reevaluation pass | the crawler exits within its deadline | handled only when the step ends |
| A `TimeoutError` outside the loops | exit 1 | exit 0, `Shutdown deadline elapsed` |
| Each driven adapter facing its outside system's real failures (file removed, disk full, connection reset, timeout, malformed or deeply nested JSON and YAML) | its port's declared failure | a raw `sqlite3.Error`, `OSError` or `RecursionError` (appendix C) |

### Lot 4b

| Check | After the lot | On `main` |
|---|---|---|
| A bug on every Kad search | the eD2k searches go on; Kad failing; the search role and the crawler degraded | the crawler stops |
| A bug on one keyword's searches | that search failing, the other keyword's searches go on, the channel degraded; the client restarted three times at most | the crawler stops |
| A unit of work past its maximum duration | a `Bug` outcome, the component goes on | the task waits forever |
| A bugs condition failing with no recovery | its state owner restarted, three useless restarts, then none | n/a |
| aMule unreachable | the channels and the download parts failing through the client, nothing restarted | the status loop alerts, nothing else |
| The pattern `000111000111` then ten successes | failing from the first period's third failure, never leaving it during the pattern, healthy again after the successes | n/a |
| The connectivity alerts | still sent, at today's entry; their end held by the hysteresis | sent by the status loop's timers, ended at the first good reading |

### Lot 4c

| Check | After the lot | On `main` |
|---|---|---|
| aMule unreachable | one alert "client unreachable" with its impact | "aMule unreachable" alone |
| Every channel not connected (the VPN down) | one message for the root causes opened together | one alert per channel |
| An open alert across a crawler restart | not sent again, listed in "node online"; its end sent when it clears | sent again after the delay |
| An open alert whose keyword was removed from the config | closed at the start | n/a |
| `/health/ready` with the crawler failing | 503, the root causes in `checks` | `/health` 200 `ok` |
| `/health/live` with the event loop blocked | 503 | `/health` 200 `ok` |
| The event loop frozen past the watchdog's timeout | the stacks in the log, exit 1, Docker restarts | the container stays up, frozen |
| A refused password at start | the client failing with that reason, the webui up | a traceback, exit 1, at every start |
| A failed migration or an unreadable database at start | one line, exit 1 | a traceback |
| A bug on one file of the reevaluation | the others judged, the fingerprint not written, a condition counting it | the start crashes, at every start |
| `/metrics` | one series per health state per component, outcomes per component and reason, no `p2pwatch_crawler_up` | `p2pwatch_crawler_up` at 1, never 0 |
| rc: faults injected on the node (aMule stopped, the VPN cut, `data/` filled past its floor, a bug injected in one channel) | each shows as its root-cause alert, the rest of the node running | n/a |

### What must not change

| Check | Observed by |
|---|---|
| The matching decisions on the real catalog | the umbrella's matching comparison: 0 decisions differ |
| `deploy/matcher.yml` and its keys | `git diff --stat main -- deploy/matcher.yml` empty, `validate-config` on `deploy/` passing |
| A healthy channel's search cadence | searches per hour on the node at rc, within appendix C's range |
| A healthy node's notifications | no health alert during an hour where every status reading shows each channel connected |

## 5. Blocks

Each lot is its own stack from `main`, its blocks numbered by tens from 10. Estimates: appendix C, re-measured at the
start of each block (4b's and 4c's blocks estimate code not yet written).

### Lot 4a

| Block | Branch | Content |
|---|---|---|
| 10 | `refactor/token-expression` | the matcher's `Condition` renamed `TokenExpression` (Corrected: every matcher identifier, comment and message built on the word, not the type alone) |
| 20 | `fix/backoff-cap` | the delay capped before computing, `factor` and `jitter_ratio` bounded |
| 30 | `feat/no-pause-webui` | pause routes, buttons, use cases removed (Corrected: re-cut by the lead, vulture refusing a port method left without caller: the pause's write side end to end) |
| 33 | `refactor/no-pause-consumers` | the loops stop reading the pause (Corrected: the read side end to end, the reader's pause half and the glossary line included, the dashboard's "The crawl is ..." line removed) |
| 36 | `refactor/no-pause-run-state` | the run state keeps the shutdown request only (Corrected: the operator pages alone, kept apart so 30 stays under 20 files) |
| 40 | `fix/decisions-one-transaction` | a file's decisions in one transaction (Corrected: no fake `DecisionWriter` existed, so none was added) |
| 50 | `fix/port-sync-rounds` | every port-sync error logged and retried |
| 60 | `fix/bounded-shutdown` | signals at start, stop grace, bounded close, exit codes (Corrected: split for the bound: 60 the exit codes, the bounded close and the grace; 62, `fix/shutdown-signals-at-start`, the signals at the start) |
| 70 | `fix/sqlite-leaks` | the SQLite adapters' leaks, their contracts (Corrected: split for the bound: 70 the webui's readers and `open_reader`; 72, `fix/sqlite-copier-leaks`, the console and the copiers; 74, `fix/sqlite-stored-value-leaks`, the stored values) |
| 75 | `fix/filesystem-leaks` | the filesystem adapters' leaks, their contracts (Corrected: split for the bound: 75 the meter, the download cycle and the opening; 77, `fix/catalog-finder-leaks`, the finder and the merge) |
| 80 | `fix/amuleapi-yaml-leaks` | the amuleapi and YAML adapters' leaks, their contracts |
| 90 | `docs/lot-4a-wrap` | closing block (Corrected: cut as `fix/lot-4a-review`, then split in four for the bounds: 90 the stop during the start and its 25 s bound, 92 and 94 the writer contracts' refused writes, the catalog's then local.db's, 96 the other findings and the records) |

### Lot 4b

| Block | Branch | Content |
|---|---|---|
| 10 | `feat/health-outcome` | `DeclaredFailure`, `Outcome`, `Health`, `HealthTransition` |
| 15 | `feat/health-condition` | `HealthCondition`, its windows and thresholds |
| 20 | `feat/health-graph` | `Component`, `Dependency`, `Quorum`, propagation |
| 25 | `feat/health-root-causes` | root causes and their impact |
| 30 | `feat/supervisor` | `Supervisor`, `run_once`, `time_limit`, bugs condition |
| 33 | `feat/restart-policy` | `RestartPolicy`, `StateOwner` |
| 36 | `feat/status-sensor` | the status loop as a sensor component |
| 40 | `feat/search-channels` | channels and searches as components |
| 45 | `feat/search-outcomes` | the search worker reports outcomes |
| 50 | `feat/download-tracking` | download tracking as a component |
| 53 | `feat/source-tracking` | source tracking as a component |
| 56 | `feat/disk-space-condition` | disk space low as a condition |
| 60 | `feat/webui-component` | the webui thread as a component |
| 65 | `feat/notifier-component` | the notifier as a component |
| 70 | `docs/lot-4b-wrap` | closing block |

### Lot 4c

| Block | Branch | Content |
|---|---|---|
| 10 | `feat/health-alerts` | one alert per root cause, with its impact |
| 15 | `feat/alert-grouping` | alerts opened together in one message |
| 18 | `feat/health-alert-notifications` | the old connectivity and disk events replaced |
| 20 | `feat/open-alerts-store` | open alerts in `local.db` |
| 25 | `feat/open-alerts-restart` | never re-announced, listed, ended, closed |
| 30 | `feat/health-metrics` | health series and outcome counters |
| 35 | `feat/crawler-up-removed` | `p2pwatch_crawler_up` removed |
| 40 | `feat/node-page-health` | the Node page shows the graph |
| 50 | `feat/health-endpoints` | started, ready, the old `/health` removed |
| 55 | `feat/health-live` | live, compose healthcheck |
| 60 | `feat/loop-watchdog` | the frozen-loop watchdog |
| 70 | `fix/start-refusals` | a failed migration refuses in one line |
| 73 | `feat/refused-password-condition` | a refused password is a client condition |
| 76 | `feat/database-components` | the databases as components |
| 80 | `fix/reevaluation-pass` | a pass complete only when every file succeeded |
| 90 | `docs/lot-4c-wrap` | closing block |

## 6. Limits and scope

### Accepted limits

- **A rare bug, once in more than ten outcomes, does not degrade its component**: it leaves its full trace in the log
  each time (D9).
- **A periodic pattern of three failures in a row reads failing**, though the part still renders half its service:
  three failures in a row cannot be told from a total outage; the alert gives the rate (D9).
- **A deterministic bug on one keyword restarts its client up to three times** before the policy stops: a few
  in-flight searches are lost each time (D5).
- **No static guarantee of the declared failures** (D6): the default `Bug`, the contracts and the rc's fault injection
  stand in for it.
- **A notification is still lost if the process dies between a decision's commit and its send, or if the notifier
  refuses it**, as today (D20).
- **The windows restart empty after a crawler restart**, unknown until they fill (D13).
- **Compose keeps `restart: unless-stopped` for `p2pwatch`**, so a refusal at start (an invalid configuration, a
  failed migration) restarts in a loop, spaced by Docker up to once a minute, its one line saying what to do: the
  policy is what revives the crawler after a watchdog exit, a death of the process and a reboot of the host (D17).
- **A wait between two units of work that never ends** is outside the supervisor's timeout; such waits are the
  supervisor's own, all bounded (D4).

### For lot 7 (umbrella D19)

- The health model: what each state means, the alerts by root cause and their impact, "node online"'s open alerts,
  the Node page's health.
- The old `/health` removed, the three MicroProfile paths; the compose healthcheck.
- The replaced connectivity and disk alerts and the removed `p2pwatch_crawler_up`, in the migration guide.
- The pause removed; the restart button kept.
- (Corrected: three new refusals of `crawler.yml`, breaking for a 4.x one: `search.backoff.factor` at most 10 and
  `search.backoff.jitter_ratio` at most 1, block 20; `shutdown_deadline_seconds` at most 25, its message naming
  compose's stop grace, the closing block. The matcher's refusal now reads `exactly one token expression
  (all/any/not) expected`, where 4.x printed `exactly one condition`, block 10. A YAML file nested too deeply or
  holding a control character is one problem of its file, `invalid YAML: ...`, block 80.)
- The new stop grace; a refused password no longer crash-loops; the frozen-loop exit and where its stacks are; the
  port-sync's errors in its log.
- The new `local.db` migration (open alerts).

### Adjacent backlog items

- **v5 release readiness**: this spec implements its sub-entries 4a, 4b and 4c; each is deleted when its lot merges.
- **Lot 5, the webui** (its sub-entry): its `/health` row ("under 100 ms while a page sleeps") and its Node page
  actions meet 4c's health paths and Node page; they stay lot 5's, since moving the database reads off the event loop
  is its subject.
- **Multi network stage 5**: D11's graph by roles prepares it, and its "free-space check per client output directory"
  will be one disk condition per download client; nothing of it is built; it stays open.
- **Contract tests for the fakes of outside systems**: D6's contract tests provoke the real failures against the real
  adapter, not the fakes against the real system; it stays open.
- **A generic way to write the tests' stubs and spies**, **test quality**, **mutation testing in the gate**: tooling
  debt, untouched; they stay open.

## Appendix A. Design, block by block

### The health library (lots 4b, 4c)

- **Its shape**, as the operator read it in the discussion (names may move with the Naming rules):

  ```python
  # domain/health: health only
  keroro_kad = Component(name="keroro on Kad", conditions=[BUGS], depends_on=[...])
  kad = Component(
      name="aMule/Kad",
      conditions=[CONNECTED, CONNECTABLE, SEARCHES_FAILED, BUGS],
      depends_on=[
          Dependency(on=(keroro_kad, titar_kad), quorum=Quorum.ANY),
          Dependency(on=(amule, catalog, local), quorum=Quorum.ALL),
      ],
  )


  # application/ports/driven: what the core sees of a state owner, an ABC like every port, with its contract
  class StateOwner(ABC):
      @abstractmethod
      async def restart(self) -> None:
          """Builds the owner anew and adds the work depending on it to the supervisor again."""


  # application/steps/supervisor.py
  class Supervisor:
      def add(self, work: Work, *, feeds: tuple[Component, ...], relies_on: StateOwner | None, time_limit: timedelta) -> None: ...

      async def _turn(self, work: Work) -> None:
          outcome = await self._outcome_of(work)
          await self._health.record(outcome, on=self._feeds[work])  # publishes the transitions

      async def _outcome_of(self, work: Work) -> Outcome:
          try:
              async with asyncio.timeout(self._time_limits[work].total_seconds()):
                  await work.run_once()
          except DeclaredFailure as failure:
              return Outcome.declared(failure)
          except TimeoutError:
              return Outcome.bug(f"past its {self._time_limits[work]}")
          except Exception as error:  # the boundary of the work, by design
              self._logger.exception("bug in %s", work)
              return Outcome.bug(repr(error))
          return Outcome.success()


  # composition: the only place holding the factories
  class AmuleClientOwner(StateOwner):
      async def restart(self) -> None:
          await self._client.close()
          self._client = AmuleApiClient(...)  # a new session, eD2k lock, Kad slots and caches
          for keyword, channel in self._searches:
              self._supervisor.add(self._build_search(keyword, channel), feeds=..., relies_on=self, time_limit=...)


  supervisor.add(
      KeywordSearch(keyword="keroro", channel=KAD, ...),  # the work, run again and again
      feeds=(keroro_kad, kad),                             # the health it feeds
      relies_on=amule_owner,                               # rebuilt when its bugs repeat
      time_limit=timedelta(minutes=3),                     # past it, a turn is a bug
  )
  ```

  A `Work` is a callback `Protocol` with `run_once()`, implemented by the core's steps, not a port. A search's outcome
  is recorded on its own component and on its channel's (`feeds`); each condition counts only
  its reasons. The health publishes each `HealthTransition` to its subscribers: the alerts (4c) and the
  `RestartPolicy`, which reads the `StateOwner` each work relies on (below). The asyncio timeout
  goes through the clock adapter in the real code.
- **Conditions** (D9, D10). Each condition counts, among a component's last outcomes, those whose reason it judges;
  a success counts for all. Its severity enters at "k failures among the last n" and leaves under "j among the last
  m", the exit stricter than the entry. Starting values, constants of the code, tuned at the release candidate:

  | Severity | Enters | Leaves |
  |---|---|---|
  | failing | 3 failures among the last 3 | fewer than 2 among the last 10 |
  | degraded | 2 failures among the last 10 | fewer than 1 among the last 20 |

  A condition is an immutable declaration; its window of outcomes is the state of the component that carries it. A
  reason is a type, a `DeclaredFailure` subclass or `Bug`, never a string, so a misspelt reason cannot count silently:

  ```python
  # the common case: the default thresholds
  BUGS = HealthCondition(name="bugs", counting=Bug)
  SEARCHES_FAILED = HealthCondition(name="searches failed", counting=SearchFailedError)

  # a particular case: the sensor, at today's entry
  NOT_CONNECTED = HealthCondition(
      name="not connected",
      counting=ChannelNotConnected,
      failing=Band(enters=AtLeast(6, of_last=6), leaves=Below(2, of_last=10)),
      degraded=None,
  )

  # the defaults, written once
  failing=Band(enters=AtLeast(3, of_last=3), leaves=Below(2, of_last=10))
  degraded=Band(enters=AtLeast(2, of_last=10), leaves=Below(1, of_last=20))
  ```

  The sensor raises nothing: a reading "Kad not connected" is an outcome whose reason is `ChannelNotConnected`, a
  `DeclaredFailure` of the domain never raised.

  The sensor's conditions count its readings, one a minute, at today's entry: not connected enters failing at 6 of 6,
  not connectable enters degraded at 6 of 6, unreachable enters failing at 3 of 3; each leaves by the table's exit. A
  condition is unknown until it holds as many outcomes as its smallest entry window. A component's health is the
  worst of its conditions and of what its dependencies give it. The short failing window and the long degraded one
  follow the SRE workbook's short and long windows.
- **Conditions per component**:

  | Component | Condition | Gives |
  |---|---|---|
  | every supervised component, each keyword search included | bugs (`Bug` outcomes) | the table's thresholds |
  | a channel | not connected (a sensor reading) | failing |
  | a channel | not connectable (a sensor reading) | degraded |
  | a channel | searches failed by the network (`SearchFailed`) | the table's thresholds |
  | the aMule client | unreachable (a sensor reading) | failing |
  | the aMule client | password refused (4c) | failing |
  | download tracking | the client connected to no network | failing |
  | download tracking | free disk space below the current floor | degraded |
  | a database | its writes' declared failures | the table's thresholds |
  | the webui | a fall of its unit, which serves until it falls | a `Bug` |
  | the notifier | its sends refused, per service | the table's thresholds |
  | the reevaluation (4c) | its files' failures | failing until a complete pass |

- **The graph for today's node** (D11). A dependency's quorum says how many of the components it names a component
  needs: **all** of them (each is required: a channel cannot work without its client), **at least one** (they are
  redundant: the search role works while one channel does), or **none** (it is optional: the crawler works without
  its webui, whose failure only degrades it). Each line below is one dependency:

  | Component | Depends on | Quorum |
  |---|---|---|
  | crawler | search, download | at least one |
  | crawler | status sensor, webui, notifier | none |
  | search | each channel (aMule/eD2k, aMule/Kad) | at least one |
  | a channel | its keyword searches | at least one |
  | a channel | the aMule client, the catalog, the local database | all |
  | a keyword search | the aMule client | all |
  | download | each download client's part (aMule) | at least one |
  | aMule (download) | download tracking, source tracking | at least one |
  | download tracking, source tracking | the aMule client, the catalog, the local database | all |
  | source tracking | download tracking | all |
  | the reevaluation (4c) | the catalog | all |

  A node without `download:` has no download branch.
- **Restarts** (D5). Each work added to the supervisor names the state owner it relies on, if any. The core sees a
  state owner as a port, `StateOwner.restart()`; the composition implements it: it closes the old object, builds a new
  one and new work from the factories it alone holds, and adds that work to the supervisor, which has cancelled the old
  work first so none keeps a reference to the old object. The owners are the aMule client (its session, its eD2k lock, its Kad
  slots, its caches; a restart closes the session, opens a new one and rebuilds every work relying on it),
  the webui thread and the notifier; the databases have none. The restart policy subscribes to the health transitions,
  like the alerts:
  1. a component's bugs condition enters failing: its owner restarts, which empties the windows of every component it
     rebuilds;
  2. a bugs condition of these components fails again with no return to healthy: that restart was useless;
  3. after three useless restarts, the policy stops for that owner, and the alert says restarting repaired nothing;
  4. a return to healthy resets the count.

  Three bugs in a row are needed to fail again, which spaces the attempts with no delay to tune; three echoes OTP's
  bounded restart intensity before it gives up. A deterministic bug on one keyword costs at most three restarts of
  its client: a few in-flight searches, aMule itself untouched.
- **Alerts** (D12, D13): an alert's key is its component and its condition; it holds its reason, severity and
  opening time, and its message names the root cause, its reason, its rate where windowed, and its impact, deduplicated.
  The grouping wait is 30 s (Alertmanager's `group_wait` default).
- **The watchdog** (D15): 5 minutes, against the longest synchronous stretch measured (8 s on the host, 65 s for the
  same answer on the node under v4, appendix C).

### Lot 4a

- **Block 10**: `Condition` in `domain/matching/config.py` and the config adapter's schemas and tests; `threading.Condition`
  is left alone; a glossary line for `TokenExpression`.
- **Block 20**: `backoff_delay` compares the exponent with the cap's (`log`) before raising; `factor` at most 10 (past
  it, a delay reaches its cap after a failure or two, a step rather than a backoff) and `jitter_ratio` at most 1 (a
  jitter above the delay itself pushes the wait toward `timedelta`'s overflow, about 8.6e13 s), each refused past its
  bound with a test at and past it; the umbrella's instrument `fault-isolation/test_backoff_overflow.py` becomes a unit
  test.
- **Blocks 30, 33, 36**: in this order, so each block is green: the web surface (routes, buttons, use cases, driving
  ports, their fakes, the docs' two mentions), then the consumers (`search_task_runner`'s `wait_until_resumed`,
  `summarize_crawl`'s `is_paused`), then the pause half of `RunStateReader` and `RunStateWriter`, their store,
  contract and fake. 29 files today (appendix C). (Corrected: cut by side instead, since vulture refuses a port method
  whose only callers leave: 30 the write side end to end, 33 the read side end to end, 36 the operator pages.)
- **Block 40**: a grouped write on `DecisionWriter`, its SQLite store, contract and fake; `FileJudge.rejudge` builds
  the changes and the event before writing; the `RuntimeError` of a file judged without an observation moves before
  any write. (Corrected: no fake existed; the judge's failure is injected by an SQLite trigger on the real store, and
  the `RuntimeError` already ran before any write.)
- **Block 50**: `PortSyncLifecycle` runs each round under a `try`: `ApiNotReadyError` and `ListenPortRejectedError`
  keep their lines, any other exception is logged with its trace, and the next poll runs; the command line still
  exits on `SettingsError`.
- **Block 60**: a flag set by a `signal.signal` handler, which runs between bytecodes even inside synchronous code,
  read between the opening's steps, by an SQLite progress handler during a migration (the interrupted block rolls back
  whole, lot 2's D1) and between the reevaluation's files, the pass also yielding the loop per file; the loop handler
  of `PosixProcess` kept for the rest; `stop_grace_period` in `deploy/compose.yml` above `shutdown_deadline_seconds`
  plus the close's bounds; the close after the deadline gets a bound of its own; `_crawl` reports the shutdown
  deadline from the composition's own signal, not from any `TimeoutError`. (Corrected: split into 60 and 62; the pass
  reads the run state, not the flag, so the webui's restart stops it too; the closing block sets the progress
  handler on every connection of the opening, the earlier copy's reader included, so the pre-migration copy, its
  comparison and the reclaim are interrupted too, and has the plain handler raise nothing, a second signal exiting 1
  at the loop's first turn instead of meeting `sqlite3`'s swallowed exception; `shutdown_deadline_seconds` is refused
  past 25 s, compose's grace minus the close.)
- **Blocks 70, 75, 80**: each leak of appendix C converted where its adapter meets its library, into its port's
  declared failure; the ports that declare none today (`FreeSpaceMeter`, `CatalogFinder`, `ConfigChecker`, the webui's
  readers) gain one, named in their block by the Naming rules; each contract provokes the real failure (a removed or
  unreadable file, a read-only or full SQLite database, a reset connection, a timeout, JSON or YAML nested past the
  recursion limit, malformed YAML) and expects the declared failure. (Corrected: 70 split into 70, 72 and 74, 75
  into 75 and 77. The console's opening failure is a `QueryFailure`, its port's only failure shape, and the merge's
  unremovable leftover is logged, the source's failure raised (72). A stored value no store writes is tested in each
  SQLite adapter's own module, a corrupt row existing in SQLite alone (74); so are the amuleapi and YAML adapters'
  leaks, the client ports and `ConfigChecker` having no contract (80). `FreeSpaceMeter` and `CatalogFinder` share one
  declared failure, `InaccessiblePathError`, the operator's answer (75); `ConfigChecker` gains none, nested and
  malformed YAML taking lot 3's path as one `ConfigProblem` (80). The writer contracts' full and read-only databases
  came in the closing block, their fakes skipping the case, memory refusing no write.)
- **Block 90**: the handoff, `BACKLOG.md`'s sub-entry 4a deleted, the holistic review's fixes. (Corrected: split into
  90, 92, 94 and 96, as section 5's table says.)

### Lot 4b

- **Blocks 10, 15, 20, 25**: `domain/health/`, pure (no I/O, the clock injected); `DeclaredFailure` at the domain's
  root, the base of every port's declared failures; tach entries; glossary lines for every D8 name; the condition's
  tests include section 4's pattern.
- **Blocks 30, 33**: `application/steps/supervisor.py` replaces `loop_supervisor.py`: it runs each unit's `run_once()`
  under a `try` and its `time_limit`, records the outcome, and keeps the shutdown's cancellation of every unit; the
  restart policy subscribes to the transitions. Block 30 is estimated at about 20 files: re-measured at its start, it
  splits between the supervisor and its wiring if it passes a bound.
- **Block 36**: the status loop becomes the sensor component; its `_AlertTimer` replaced by conditions whose
  transitions emit today's events (`ClientUnreachableLasting`, `ChannelDegraded` and their ends) until lot 4c; the
  status loop's tests updated for the hysteresis's ends.
- **Blocks 40, 45**: a component per (client, channel) and per keyword search; the search worker lets
  `SearchFailedError` and `ClientUnreachableError` through after updating the backoff, as today; the backoff registry
  unchanged.
- **Blocks 50, 53, 56**: the download cycle split in download tracking and source tracking; `DiskSpaceLow` produced by
  the free-space condition's transitions until lot 4c.
- **Blocks 60, 65**: the webui thread as a unit restarted by the restart policy; the notifier's sends as outcomes per
  service.
- **Block 70**: the handoff, `BACKLOG.md`'s sub-entry 4b deleted, the holistic review's fixes.

### Lot 4c

- **Blocks 10, 15, 18**: `HealthAlert` and the grouping in the domain; the five events `ChannelDegraded`,
  `ChannelRecovered`, `ClientUnreachableLasting`, `ClientReachableAgain`, `DiskSpaceLow` replaced; the apprise texts.
- **Blocks 20, 25**: a `local.db` migration for the open alerts (component, condition, reason, severity, opened at), its
  port pair, store, contract and fake; at the start, the open alerts are loaded, those of a component absent from the
  graph closed, the others held until their condition is known; "node online" lists them.
- **Blocks 30, 35**: a gauge per component and health state (one series per state, 0 or 1, as resilience4j exposes a
  breaker's state), a counter of outcomes per component and reason, labelled by client, channel and keyword where they
  apply; `p2pwatch_crawler_up` removed; the fixtures of the old Prometheus text updated.
- **Block 40**: the Node page lists every component, its health, its reason and since when.
- **Blocks 50, 55**: the MicroProfile paths and JSON; the event loop's heartbeat, a monotonic instant the webui thread
  reads; the compose healthcheck on live.
- **Block 60**: `faulthandler.dump_traceback_later(timeout, exit=True)` armed once the graph runs and re-armed at each
  beat; its timeout a constant.
- **Blocks 70, 73, 76**: `MigrationError` and `PersistenceError` at start refused in one line by the command line; the
  status sensor no longer re-raises `ClientAuthError`, the startup open tolerates it, the client's password condition
  fails; the two databases as components fed by their writes' outcomes.
- **Block 80**: `CatalogReevaluator` judges each file under its own `try` (a declared failure keeps its reason, any
  other exception is a `Bug`), writes the fingerprint only when every file succeeded, and its condition counts the
  failures; the reevaluation is a component depending on the catalog, run before the graph's units start.
- **Block 90**: the handoff, `BACKLOG.md`'s sub-entry 4c deleted, the holistic review's fixes.

## Appendix B. Acceptance, in detail

| Row | Command, and the output that fails it |
|---|---|
| 1025th failure | a unit test from `agents/reference/2026-11-04-v5-audit-instruments/fault-isolation/test_backoff_overflow.py`; fails on `OverflowError` |
| Bounds | `validate-config` on a `crawler.yml` with `factor: 11`, then `jitter_ratio: 1.5`; fails if either prints no problem for its key, or if `factor: 10` and `jitter_ratio: 1` are refused |
| Pause removed | a webui test posting `/controls/pause`; fails on anything but 404 or 405 |
| One transaction | a `FileJudge` test whose decision store fails on the second write; fails if any decision of the file is read back, or if the next judgement does not dispatch |
| Port-sync rounds | a lifecycle test whose listen-port client raises a 401, a 404, a malformed body and a `RuntimeError` in turn; fails if the loop ends or a round is skipped after them |
| SIGTERM during a step | `agents/reference/2026-11-09-v5-lot4-instruments/test_lot4_extra.py`'s reevaluation probes, turned into tests that signal the process during a migration and at the first file of a pass; fail if the process has not exited within its deadline |
| `TimeoutError` outside the loops | a `_crawl` test raising `TimeoutError` from the startup; fails on exit 0 |
| Leaks | each adapter's contract, provoking its outside system's real failure; fails on any exception other than the port's declared failure |
| Kad bug | the umbrella's probe `test_a_kad_bug_stops_the_working_ed2k_tasks_too`, inverted; fails if the eD2k searches stop |
| One keyword's bug | a supervisor test with two keywords, one raising at every search; fails if the other keyword's searches stop, or if the client is restarted more than three times |
| `time_limit` | a unit whose `run_once` never returns; fails if no `Bug` outcome is recorded within its timeout |
| Restart policy | a component failing on bugs with no recovery; fails unless exactly three restarts of its owner happen, then none |
| aMule unreachable (4b) | a graph test; fails if any owner is restarted or if the channels are not failing |
| `000111000111` | a condition test feeding the pattern ten times, then ten successes; fails if the condition is not failing from the first period's third failure, leaves failing during the pattern, or is not healthy after the successes |
| Connectivity alerts in 4b | the status loop's tests, their ends updated to the hysteresis; fail if an event is not emitted at today's entry |
| One alert per root cause | a graph and alert test, the client unreachable; fails on more than one alert or a missing impact |
| VPN down | every channel not connected within the grouping wait; fails on more than one message |
| Restart with an open alert | an alert store test across two lifecycles; fails on a second opening notification, on "node online" not listing it, or on no end once the condition clears |
| Removed component | an open alert of a keyword absent from the new config; fails if it is still open after the start |
| `/health/ready` | a webui test with the crawler failing; fails on 200 or on root causes missing from `checks` |
| `/health/live` | a webui test with a stale heartbeat; fails on 200 |
| Watchdog | a subprocess test blocking its loop past a short timeout; fails if the process does not exit 1 with a stack on stderr |
| Refused password | a composition test with an amuleapi refusing the password; fails on an exit, or if the client's condition is not failing |
| Start refusals | `_crawl` tests raising `MigrationError`, then `PersistenceError`, at opening; fail on a traceback or on more than one line |
| Reevaluation bug | a reevaluator test with one file raising; fails if another file is not judged or if the fingerprint is written |
| `/metrics` | a Prometheus text test; fails if a component lacks a state series or an outcome counter per reason, or if `p2pwatch_crawler_up` remains |
| rc fault injection | on the node: `docker compose stop ed2k`; gluetun's VPN cut; a file filling `data/` past the floor; a bug injected in the Kad channel by a test image; fails on a stopped crawler, a missing alert, or an alert per channel where the cause is one |

## Appendix C. Facts

Measured 2026-11-09 on `main` at `629fdb03`; the teammates' full reports are in the lead's gitignored `.reviews/v5-lot4-*.md`.

### The inventory

- The audit's 12 fault-isolation probes pass unchanged (`12 passed`): every behaviour of the umbrella's appendix A "Lot
  4" still holds; the Kad probe ran 936 to 954 eD2k searches before the stop (812 at the audit: scheduling, not
  behaviour).
- `LoopSupervisor` runs the search runner, the status loop and, with `download:`, the download loop in one
  `TaskGroup` (`loop_supervisor.py:33`); the search runner runs one task per (client, channel, keyword) in a second
  one (`search_task_runner.py:51`). Any escaping error leaves `__main__` as an `ExceptionGroup`, a raw traceback, exit
  1, with no notification.
- The eD2k lock and the Kad slots are attributes of `AmuleApiClient` (`amule_api_client.py:103,105`), shared by both
  channels; the backoff is one `BackoffRegistry`, shared by every task and persisted after each search that changed it.
- Source points are written to the catalog (`crawler_composition.py:466`), and download tracking reads the catalog's
  observations and decisions.
- `p2pwatch_crawler_up` is set to 1 by `CrawlerStarted` and never to 0 (`git grep -n -w CRAWLER_UP -- packages/crawler/src`:
  2 sites).
- `/health` answers `{"status": "ok"}` without checking anything (`adapters/driving/webui/app.py:800`); `p2pwatch` has
  no healthcheck and no `stop_grace_period` in `deploy/`.
- `PosixProcess` installs loop signal handlers (`posix_process.py:24-28`): a request is seen only when the loop runs;
  the opening and the migrations are synchronous calls on the loop's thread, and a pass that changes no decision
  never yields (the inventory's added probe: "requested seen at any file: False").
- The reevaluation writes its fingerprint only at the end of the pass (`catalog_reevaluator.py:54`); a `StoreError`
  on a file is logged and the file skipped (`:73`), the fingerprint written anyway.
- The file judge writes each decision in its own call, then dispatches (`file_judge.py:75-99`).
- The port-sync's `_log_in` treats only a 503 as "not ready" (`amule_api_listen_port_client.py:74-78,122-125`); any
  other `ListenPortError` ends the loop and the container.
- `factor` and `jitter_ratio` have no upper bound (`crawler_config_schema.py:57-58`).
- The pause surface: `git grep -l -w -E "PauseCrawl|ResumeCrawl|pause_crawl|resume_crawl|is_paused|set_paused|wait_until_resumed|controls/pause|controls/resume|CrawlPauser|CrawlResumer|crawl_pauser|crawl_resumer" | grep -v '^agents/' | wc -l`: 29 files.
- The run state is in memory and starts running (`asyncio_run_state_store.py:27`): a pause is lost at every restart.

### Leaks of declared failures

Proven on samples: `sqlite3.Error` raw from the webui's four readers, `open_reader` and `SqliteSqlExecutor`'s opening;
`OSError` raw from `ShutilFreeSpaceMeter` (`FileNotFoundError`) and `FilesystemCatalogFinder` (`PermissionError`);
`RecursionError` from `json.loads` in `AmuleApiClient.status()` and from PyYAML in `load_yaml`. From code reading:
`open_in_memory`, the pre-migration and catalog copiers' cleanups, `sqlite_catalog_copier`'s `_check_catalogs`
(`create_function`), `ValueError` and `OverflowError` when decoding stored values. Unverified: what
`httpx.AsyncClient(...)`, `transport_factory()` and `aclose()` raise outside `_send`.

### Cadence (outcomes per hour, current code, shipped config: 2 keywords, 1 client)

| Unit | Healthy | Failing (backoff 300 to 390 s) |
|---|---|---|
| a keyword on eD2k | 15 to 30 | 9 to 12 |
| a keyword on Kad | 36 to 60 (21 if every search runs to its 120 s budget) | 9 to 12 |
| the eD2k channel | 30 to 60 | 18 to 24 |
| the Kad channel | 72 to 120 | 18 to 24 |
| status readings | 60 | 40 to 60 (a reading spending up to 30 s in timeouts) |
| download cycles | 90 to 120 | 90 to 120 |
| source rounds | 10 to 12 | 10 to 12 |

Observed under v4 (300 s cycle, 30 s budget): 12 per hour per keyword and channel, steady over 24 h stretches;
aMule's log shows 23 to 25 Kad searches per hour over 32 h. v5's cadence has never run on the node: unverified until rc.

### Timings

On the host (Ryzen 5 7600X, NVMe, Python 3.13.6), the real catalog migrated, the shipped policy:

- A startup reevaluation pass (2 162 files): median 7.42 s on a fresh copy (7.35 to 7.54 s, 6 runs), 6.64 s on the
  next passes, 8.86 s with a policy changing 29 verdicts. The whole pass is one synchronous stretch; 97 % of it is
  `MatchingEngine.evaluate_file`. It grows with the catalog.
- A large answer catalogued: 639 files, median 7.81 s (7.74 to 8.18 s, 16 runs); 1 219 files, median 8.05 s. The whole
  answer is one synchronous stretch; per file median 1.4 ms, max about 150 ms.
- On the node under v4, the same 639-row answer spanned 64.7 s of `observed_at`; v4's cataloguing p90 was 50 s.
- The first start on the operator's catalog (umbrella appendix B, 2026-11-04): the copy 380 s, migration 0007 225 s,
  each one synchronous stretch of the loop.
- The node's hardware and the image's Python are not measured.

### Static tooling for exceptions

| Tool | What it checks | Verdict |
|---|---|---|
| ruff DOC501/DOC502 (preview in 0.17.3), pydoclint 0.12.0 | a docstring's `Raises:` against the `raise` written in the body | blind to callees and library calls |
| mypy | nothing: mypy#11282 closed as not planned ("requires a new PEP") | none |
| deal 4.24.6 | propagates across functions and modules | blind to sqlite3, httpx, `open()` |
| CodeQL 2.27.4 | propagates raised types across calls | library calls opaque: "no type inferred" on 90 of 186 (method, type) rows of the driven adapters, both proven leaks among them |
| Pyre, pytype | | archived (pytype stops at Python 3.12) |
| pyright, basedpyright, pyrefly | lexical checks only | no propagation |
| py-checked-exceptions 0.1.0 | | excluded by the operator (young, little known), not run |
| errors as values (unions, `match`, `assert_never`) | every caller handles every declared failure | the other direction: an adapter may still leak; 44 of 76 port methods and about 81 `pytest.raises` to rewrite |

typeshed's `stdlib/sqlite3/__init__.pyi` holds no `raise`; CodeQL's `Exceptions.qll`: "Information is unavailable
for C code in general".

### Sources

| Claim | Source |
|---|---|
| The part that must be correct, supervision trees | Armstrong 2003, https://erlang.org/download/armstrong_thesis_2003.pdf |
| Restart intensity 1 in 5 s by default; past it the supervisor ends its children and itself | https://www.erlang.org/doc/apps/stdlib/supervisor.html |
| `heart`, an external watcher of the VM, 60 s by default | https://www.erlang.org/doc/man/heart.html |
| Most faults transient, tolerated by re-execution (1 Bohrbug in 132 software faults) | Gray 1985, https://jimgray.azurewebsites.net/papers/TandemTR85.7_WhyDoComputersStop.pdf |
| Crash-only software | Candea and Fox 2003, https://static.usenix.org/events/hotos03/tech/full_papers/candea/candea_html/index.html |
| A task group cancels a failed child's siblings | https://docs.python.org/3.13/library/asyncio-task.html#task-groups |
| Liveness, readiness and startup probes; liveness independent of dependencies | https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/ |
| Conditions: type, status, reason, message, lastTransitionTime | https://github.com/kubernetes/community/blob/master/contributors/devel/sig-architecture/api-conventions.md |
| Status order DOWN, OUT_OF_SERVICE, UP, UNKNOWN (from `Status.java`); DOWN and OUT_OF_SERVICE answer 503 | https://docs.spring.io/spring-boot/reference/actuator/endpoints.html |
| Count and time windows, `minimumNumberOfCalls` | https://resilience4j.readme.io/docs/circuitbreaker |
| Grouping, inhibition, `group_wait` 30 s by default | https://prometheus.io/docs/alerting/latest/alertmanager/, https://prometheus.io/docs/alerting/latest/configuration/ |
| Multiwindow alerts; low-traffic services grouped | https://sre.google/workbook/alerting-on-slos/ |
| Restarts worsen a cascade | https://sre.google/sre-book/addressing-cascading-failures/ |
| A child behind a failed parent is UNREACHABLE; its notifications suppressed only when configured (Nagios), by default (Icinga 2) | https://assets.nagios.com/downloads/nagioscore/docs/nagioscore/4/en/networkreachability.html, https://icinga.com/docs/icinga-2/latest/doc/09-object-types/ |
| Series, parallel and k-out-of-n blocks | https://en.wikipedia.org/wiki/Reliability_block_diagram (IEC 61078 not read: paid) |
| MicroProfile Health 4.0's paths, conjunction, 200 and 503, `status` and `checks` | https://download.eclipse.org/microprofile/microprofile-health-4.0/microprofile-health-spec-4.0.html |
| `faulthandler.dump_traceback_later` | https://docs.python.org/3.13/library/faulthandler.html |
| Docker does not restart an `unhealthy` container | no explicit sentence in Docker's docs; https://docs.docker.com/reference/dockerfile/#healthcheck mentions no restart, and https://github.com/willfarrell/docker-autoheal exists for it |
| Resilience by decoration at the composition root | https://blog.ploeh.dk/2024/09/02/keeping-cross-cutting-concerns-out-of-application-code/ |
| Timeouts on every integration point | Nygard, *Release It!*: unverified in the book (publisher 403), quoted second-hand by https://github.com/App-vNext/Polly/wiki/Timeout |

### Estimates

From `.reviews/v5-lot4-estimate.md` (Sonnet, 2026-11-09), before the cut: 23 draft blocks, 41 once those passing a
bound are split, one closing block among them, 43 with one closing block per lot. Tight: 4a's 40 and 60, 4c's 40. The
supervisor block (4b's 30) is about 20 files.

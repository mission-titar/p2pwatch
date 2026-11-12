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
  rule.* (Corrected: a work carries its turn and its wait before the next turn, the backoff, the status period, the
  poll or the wake; the supervisor awaits the wait outside the limit, as Kubernetes keeps a probe's period apart
  from its timeout, since a backoff wait inside the turn would end as a `Bug`; the operator's answer of
  2026-11-11.) Lot 4b.
- **D5. A bug repeated on a component restarts what holds its in-memory state (the client, the webui, the
  notifier), at most three times in vain; the composition restarts it by building it anew.** *A restart can only clear
  memory: a session, a lock, a cache, a thread; Gray found most production faults pass when the work is re-executed.
  An object built anew is fresh by construction, where a reset in place drifts with each attribute added; and an
  object's lifetime is its composition root's business (Seemann and van Deursen), so no factory leaves it. A failure a port declares (the network, aMule,
  the disk) is not repaired by a restart, which only worsens a cascade (Kubernetes, the SRE book).* (Corrected: a
  rebuild that raises leaves the owner's components failing and is tried again, counted useless, the node running
  on, the operator's answer of 2026-11-11; appendix A, "Restarts".) The rules, appendix A. Lot 4b.
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
  turn a call to `run_once()`.** (Corrected: `Work` an ABC holding its turn and its wait; `run_once()` without argument;
  one `HealthRecorder` publishing the transitions; the operator's answers of 2026-11-11, appendix A "Lot 4b, settled
  at its start".) *Each concept is taken from a reference that settled it (Spring, resilience4j, Kubernetes,
  Alertmanager, OTP, reliability block diagrams); a generic word another concept already uses is qualified on both
  sides: the matcher's `Condition` becomes `TokenExpression`.* Lot 4b, the rename in lot 4a.
- **D9. A condition counts failures among a component's last outcomes, with one threshold to enter a state and a
  stricter one to leave it.** *A count measures each component at its own pace, where a time window would leave a
  rarely used one unknown forever; two thresholds stop a periodic pattern from flapping. A single failure stays a
  log line.* (Corrected: the free-space condition enters at 1 of 1, today's `DiskSpaceLow` entry, which D21 keeps
  in lot 4b: a measurement of the disk is no noisy probe.) The values, appendix A. Lot 4b.
- **D10. Every supervised component, each search included, carries a bugs condition counting `Bug` outcomes only; its
  other conditions count their own reasons, and a success counts for all.** *The restart policy reads that condition
  alone, so a part failing for mixed reasons is never restarted for a network outage, and always for a bug.*
  (Corrected: each condition keeps its own window, fed by its own source only, a success counting for every
  condition of its source, as each Kubernetes condition is set by its own controller; the operator's answer of
  2026-11-11, appendix A "Its shape".) Lot 4b.
- **D11. One acyclic graph with one relation, "depends on", and a quorum per dependency (all, at least one, none): a
  component is failing when a quorum is not met, degraded when a dependency is degraded or failing; an unknown
  dependency degrades nothing.** *Fault trees and reliability block diagrams express series and parallel parts with one
  k-out-of-n structure, where a tree with clients and sensors set beside it was two mechanisms; a component receives
  its dependencies already built, so a cycle cannot be written; an unknown dependency degrading its parent would read
  the whole node degraded at every start.* The graph follows the node's roles, search and download, not its programs,
  so BitTorrent's two programs will fit it; the clients, the status sensor, the webui, the notifier and the databases
  are components like the others (appendix A). (Corrected: built in lot 4c, with its first reader, the health gauges:
  nothing in lot 4b reads a component's propagated health, the restart policy and today's alerts reading their own
  conditions; lot 4b's components carry their conditions without dependencies.) Lot 4c.

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
  the operator sees being an alert's end, now held by the hysteresis; 4c replaces the surfaces.* (Corrected: lot 4b
  holds the supervisor, its works, the conditions and the restarts, the graph and the root causes lot 4c's. Lot 4b
  also changes what the operator sees: a password refused while the node runs no longer stops it, each health
  change in the log, a failed search logged by the worker and the supervisor, a node restarted within a minute of
  a search holding that channel's first search until the spacing ends (Corrected 2026-11-12: in place of a
  minute's wait at every start); no release ships between the two lots.)

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

(Corrected: the rows reading a propagated health moved to lot 4c with the graph, D11; the rows from "Two status
fields" down added by the re-cut of 2026-11-11.)

| Check | After the lot | On `main` |
|---|---|---|
| A bug on every Kad search | the eD2k searches go on; every Kad search's bugs condition failing | the crawler stops |
| A bug on one keyword's searches | that search failing, the other keyword's searches go on; the client restarted three times at most | the crawler stops |
| A unit of work past its maximum duration | a `Bug` outcome, the component goes on | the task waits forever |
| A bugs condition failing with no recovery | its state owner restarted, three useless restarts, then none | n/a |
| aMule unreachable | the client's unreachable condition failing, nothing restarted | the status loop alerts, nothing else |
| The pattern `000111000111` then ten successes | failing from the first period's third failure, never leaving it during the pattern, healthy again after the successes | n/a |
| The connectivity alerts | still sent, at today's entry; their end held by the hysteresis | sent by the status loop's timers, ended at the first good reading |
| Two status fields of one channel, one failing, the other healthy, reading after reading | the failing one's alert at its own entry, six readings | n/a |
| An unknown reading between two runs of failed readings | no end sent, no second alert | no end, no second alert |
| A client restart under an open connectivity alert | the alert neither sent again nor ended by the restart | n/a |
| A work raising a bug at once, turn after turn | two of its turns never closer than the floor after a `Bug` | the crawler stops |
| A rebuild of the client that raises | the client's components failing, the rebuild tried again after the floor, three times at most, the node running | n/a |
| A password refused while the node runs | a declared outcome each turn, the node running | the crawler stops, at every start |
| Ten eD2k keywords queued on the client's lock | no turn past its time limit | n/a, no limit |
| A channel backed off when the node restarts | its first search after the persisted wait | its first search after the persisted wait |
| A client rebuilt, or the node restarted, within a minute of a search start (Corrected: added 2026-11-12) | its next start one spacing after that start, none delayed when no start is due | a restart forgets the last start |

### Lot 4c

| Check | After the lot | On `main` |
|---|---|---|
| A bug on every Kad search (Corrected: from lot 4b, with the graph) | Kad failing; the search role and the crawler degraded | the crawler stops |
| A bug on one keyword's searches (Corrected: from lot 4b, with the graph) | the channel degraded | the crawler stops |
| aMule unreachable (Corrected: the propagation from lot 4b, with the graph) | the channels and the download parts failing through the client | the status loop alerts, nothing else |
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
| 95 | `refactor/sqlite-immediate-transaction` | (Corrected: added below 96 on the operator's request in the review of #701, the stack taken to 20 blocks, past the workflow's 19, accepted by the operator on 2026-11-10) the stores' write transaction in one context manager |

### Lot 4b

(Corrected: re-cut by consumer at the lot's start, the operator agreeing on 2026-11-11: each block brings the health
pieces its first user needs, with that user, where the first table opened with four blocks of pure domain no
production code reached. The graph and the root causes move to lot 4c; three pairs merge past a bound rather than
leave code for one block without its user ("On fusionne les paires de blocs"); the stack of 22 rows, past the
workflow's 19, is accepted by the operator on 2026-11-11 ("Je préfère un seul lot"). The reasons, appendix A "Lot 4b";
the figures, appendix C "Estimates".)

| Block | Branch | Content |
|---|---|---|
| 10 | `refactor/node-id-at-construction` | the node id resolved by the composition before the graph, every step receiving it at construction (past the file bound, accepted) |
| 20 | `feat/client-unreachable-condition` | the health library's first pieces, the central recorder and its log line, the translator; the client's unreachable condition replaces the status loop's API timer (past both bounds, accepted) |
| 25 | `feat/channel-conditions` | the channels' not connected and not connectable conditions; `_AlertTimer` removed |
| 30 | `refactor/status-work` | `Work`; `LoopSupervisor` renamed `Supervisor`; the status reading the first work |
| 33 | `refactor/download-tracking-work` | download tracking as a work; `DownloadLoop` removed |
| 34 | `refactor/source-tracking-work` | source tracking as a work of its own |
| 36 | `refactor/search-works` | one work per client, channel and keyword; `SearchTaskRunner` removed |
| 38 | `refactor/supervisor-runs-the-works` | the turn loop in the supervisor, the shutdown its own |
| 40 | `feat/turn-outcomes` | each turn's outcome, a bug failing its turn alone, the floor after a `Bug` |
| 45 | `fix/amuleapi-request-bound` | a request's total bound (Corrected: the first starts' spacing moved to block 46, the operator's answer of 2026-11-12) |
| 46 | `feat/persisted-search-starts` | each client's latest search starts kept in `local.db`, a client built anew spacing its first starts from them (past both bounds, accepted by the operator on 2026-11-12) |
| 47 | `feat/turn-time-limits` | each work's time limit |
| 50 | `feat/bugs-condition` | the bugs condition and every work's component |
| 51 | `feat/network-conditions` | a channel's searches failed, download tracking's client connected to no network |
| 52 | `feat/restart-policy` | `StateOwner`, `RestartPolicy`, the aMule client's owner, useless restarts counted, none past three (past the line bound, accepted) |
| 60 | `feat/disk-space-condition` | disk space low as a condition |
| 65 | `feat/webui-liveness` | the webui's liveness turn |
| 68 | `feat/webui-restart` | the webui thread's owner |
| 70 | `feat/notifier-outcomes` | each notification's outcome recorded |
| 72 | `feat/notifier-owner` | the notifier's owner |
| 74 | `feat/notifier-services` | the notifier's services, one component each, their sends refused |
| 90 | `docs/lot-4b-wrap` | closing block |

### Lot 4c

(Corrected: 05 and 07 added and block 10 grown by lot 4b's re-cut of 2026-11-11, each moved piece with its first
reader; 18 blocks.)

| Block | Branch | Content |
|---|---|---|
| 05 | `feat/health-graph` | `Dependency`, `Quorum.ALL`, the propagation, the health gauges its first reader |
| 07 | `feat/health-graph-quorums` | the other quorums, today's whole graph |
| 10 | `feat/health-alerts` | the root causes and one alert per root cause, with its impact |
| 15 | `feat/alert-grouping` | alerts opened together in one message |
| 18 | `feat/health-alert-notifications` | the old connectivity and disk events replaced |
| 20 | `feat/open-alerts-store` | open alerts in `local.db` |
| 25 | `feat/open-alerts-restart` | never re-announced, listed, ended, closed |
| 30 | `feat/health-metrics` | outcome counters (Corrected: the health series moved to 05) |
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
  supervisor's own, all bounded (D4). (Corrected: each wait is the work's own, the backoff capped, the status
  period and the poll constants of the config.)
- (Corrected: this limit and the five below added by lot 4b's re-cut of 2026-11-11.) **While the client is
  unreachable, the channels' windows keep their last readings**: an unknown reading records nothing, so a channel's
  conditions hold what they read before the outage. Today's timer restarts its entry at an unknown reading, so a
  channel failing five readings, then unknown, then failing alerts at its next failed reading, where today it alerts
  five minutes later.
- **From lot 4b's block 40 to lot 4c's block 73, a password refused while the node runs stops nothing and alerts
  nothing**: a declared outcome each turn, the searches failing, a line in the log; no release ships between the two
  lots.
- **A turn that grows past its limit's allowance is cut as a `Bug`**: the download works grow with the tracked
  downloads and their sources, a search with the files of its answer, none bounded by a setting; a lost-media node
  tracks few downloads, so the allowance covers them (the operator, 2026-11-11), and a node past it would see its
  client restarted up to three times for a healthy turn.
- **Transitional code, each piece named in its pull request**: from block 30 to block 38, `Work.run()` drives each
  work's turns, about 15 lines block 38 moves into the supervisor; in block 38 an exception of a turn still ends the
  node, as today, until block 40; from block 36 to block 40, `BackoffSaver` saves after each turn, then in a
  `finally`.
- **A webui or notifier component without its owner** (blocks 65 and 70) is only logged when its bugs condition
  fails, until its owner arrives in the next block.

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
- The new `local.db` migration (open alerts). (Corrected: and lot 4b's block 46, the `latest_search_starts` table; a
  node restarted within a minute of a search holds that channel's first search until the spacing ends.)

### Adjacent backlog items

- **v5 release readiness**: this spec implements its sub-entries 4a, 4b and 4c; each is deleted when its lot merges.
- **Lot 5, the webui** (its sub-entry): its `/health` row ("under 100 ms while a page sleeps") and its Node page
  actions meet 4c's health paths and Node page; they stay lot 5's, since moving the database reads off the event loop
  is its subject.
- **Multi network stage 5**: (Corrected: lot 4b's block 46 writes its latest search starts by client, channel and
  scope, for its clients too.) D11's graph by roles prepares it, and its "free-space check per client output directory"
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
          """Builds the owner anew; the works relying on it, if any, are added to the supervisor again."""  # (Corrected)


  # application/steps/work.py (Corrected: an ABC holding the turn and the wait before the next one, D4, D8)
  class Work(ABC):
      @abstractmethod
      async def run_once(self) -> None: ...

      @abstractmethod
      async def wait_for_next_turn(self) -> None: ...


  # application/steps/supervisor.py
  class Supervisor:
      def add(self, work: Work, *, feeds: tuple[Component, ...], time_limit: timedelta) -> None: ...

      async def _run(self, work: Work) -> None:
          while True:
              await self._wait(work)  # outside the limit, the first turn included; a floor after a Bug
              outcome = await self._outcome_of(work)
              for component in self._feeds[work]:  # the turn's outcome feeds the bugs conditions alone
                  await self._recorder.record(outcome, on=component, by=TURNS)  # subscribers awaited in order

      async def _outcome_of(self, work: Work) -> Outcome:
          try:
              # (Corrected: raced against MonotonicClock.sleep, asyncio.timeout being refused in the core)
              await self._within(work.run_once(), limit=self._time_limits[work])
          except DeclaredFailure as failure:
              self._logger.warning("%s: %s", work, failure)
              return Outcome.declared(failure)
          except TurnPastItsLimit:
              self._logger.error("%s: past its %s", work, self._time_limits[work])
              return Outcome.bug(f"past its {self._time_limits[work]}")
          except Exception as error:  # the boundary of the work, by design
              self._logger.exception("bug in %s", work)
              return Outcome.bug(repr(error))
          return Outcome.success()


  # composition: the only place holding the factories, and naming each component's owner
  class AmuleClientOwner(StateOwner):
      async def restart(self) -> None:
          # the supervisor has cancelled and awaited the works feeding this owner's components
          await self._client.close()
          self._client = AmuleApiClient(...)  # a new session and caches, its first starts spaced from the persisted ones (Corrected)
          # every object holding the client built anew, each work added again
          for work, feeds, time_limit in self._build_works(self._client):
              self._supervisor.add(work, feeds=feeds, time_limit=time_limit)


  supervisor.add(
      KeywordSearch(keyword="keroro", channel=KAD, node_id=node_id, ...),  # the work, run again and again
      feeds=(keroro_kad, kad),                             # the health it feeds
      time_limit=search_time_limit(config),                # past it, a turn is a bug (Corrected: derived, block 47)
  )
  owners = {keroro_kad: amule_owner, kad: amule_owner, ...}  # read by the restart policy
  ```

  (Corrected: the paragraph below and the sketch's `Work`, `_run`, `_outcome_of`, the owner and the mapping, by lot
  4b's re-cut of 2026-11-11, `relies_on` removed.) A `Work` is an ABC of the core's steps, not a port. Every outcome
  is recorded through one `HealthRecorder`, in `application/steps/`, on one component and by one source; each
  condition declares the source it reads (`TURNS`, the supervisor's outcome of a turn, read by the bugs condition
  alone; the status reading's API answer, its `connected` field, its `connectable` field; a search's declared
  outcome; the free-space reading; a notification's outcome), so a success counts for every condition of its source
  and for no other. The recorder publishes each `HealthTransition` to its subscribers, awaited in order, and writes
  it in one log line: the `HealthEventTranslator` to today's events (4b), the `RestartPolicy`, the alerts (4c). A
  declared reason carries its reading (`free_bytes` and `min_free_bytes` for the free space), a component its labels
  (`client_name`, `channel`), from which the translator builds today's events. The composition names each
  component's owner; the policy reads that mapping, and the works a restart cancels are those feeding the owner's
  components.
- **Conditions** (D9, D10). Each condition counts, among a component's last outcomes, those whose reason it judges;
  a success counts for all (Corrected: each condition keeps its own window, fed by its own source only, a success
  counting for every condition of its source, D10). Its severity enters at "k failures among the last n" and leaves under "j among the last
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
  worst of its conditions and of what its dependencies give it (Corrected: lot 4c's, with the graph, nothing in 4b
  reading it). The short failing window and the long degraded one
  follow the SRE workbook's short and long windows.
- **Conditions per component**:

  | Component | Condition | Gives |
  |---|---|---|
  | every supervised component, each keyword search included | bugs (`Bug` outcomes) | the table's thresholds |
  | the status sensor (Corrected: the status work's component, its owner the aMule client's) | bugs | the table's thresholds |
  | a channel | not connected (a sensor reading) | failing |
  | a channel | not connectable (a sensor reading) | degraded |
  | a channel | searches failed by the network (`SearchFailed`) (Corrected: block 51, the search's declared outcomes its source) | the table's thresholds |
  | the aMule client | unreachable (a sensor reading) | failing |
  | the aMule client | password refused (4c) | failing |
  | download tracking | the client connected to no network (Corrected: block 51, recorded by the status reading) | failing |
  | download tracking | free disk space below the current floor (Corrected: entering at 1 of 1 and leaving at the first good reading, today's, D9) | degraded |
  | a database | its writes' declared failures | the table's thresholds |
  | the webui | a fall of its unit, which serves until it falls (Corrected: a liveness turn each period, a fallen thread a `Bug`: no asyncio cancellation reaches a thread, D4) | a `Bug` |
  | the notifier | its sends refused, per service (Corrected: one component per service, block 74; a refusal `NotificationRefused`, a timeout `NotificationTimedOut`, both declared, any other exception a `Bug`. Corrected by lot 4b's closing block: "sends failed", counting a timeout as a refusal, both a `NotificationFailed`, so a service that only times out fails; the operator's answer of 2026-11-12, "on ne gagne pas à distinguer") | the table's thresholds |
  | the reevaluation (4c) | its files' failures | failing until a complete pass |

- **The graph for today's node** (D11; Corrected: built in lot 4c, blocks 05 and 07). A dependency's quorum says how many of the components it names a component
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
- **Restarts** (D5). Each work added to the supervisor names the state owner it relies on, if any (Corrected: the
  composition names each component's owner, the works an owner's restart cancels being those feeding its
  components). The core sees a
  state owner as a port, `StateOwner.restart()`; the composition implements it: it closes the old object, builds a new
  one and new work from the factories it alone holds, and adds that work to the supervisor, which has cancelled the old
  work first so none keeps a reference to the old object. The owners are the aMule client (its session, its eD2k lock, its Kad
  slots, its caches; a restart closes the session, opens a new one and rebuilds every work relying on it),
  the webui thread and the notifier; the databases have none. The restart policy subscribes to the health transitions,
  like the alerts:
  1. a component's bugs condition enters failing: its owner restarts, which empties the windows of every component it
     rebuilds (Corrected: the bugs conditions' windows only: emptying a sensor condition's would lose an open
     connectivity alert's end or send it twice; the restart runs in a task of the supervisor, never in the turn that
     triggered it, which it cancels; a rebuild that raises records a `Bug` on each of the owner's components and
     is tried again after the floor, each failure counted useless, the operator's answer of 2026-11-11);
  2. a bugs condition of these components fails again with no return to healthy: that restart was useless;
  3. after three useless restarts, the policy stops for that owner, and the alert says restarting repaired nothing;
  4. a return to healthy resets the count (Corrected: when every bugs condition of the owner's components is healthy
     again, the owner then repaired; after three useless restarts the node runs on, its webui up, the owner's
     components failing, nothing of the owner's work running until the container restarts).

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
- **Block 95** (Corrected: added on the operator's request in the review of #701, the lot's 20 blocks accepted by the
  operator on 2026-11-10): `immediate_transaction(connection)`, the SQLite adapter's one write transaction, used by
  the backoff, decision, source point, tracked download and observation stores, each of its three placements
  commented and provoked by a test: `BEGIN IMMEDIATE` outside the `try`, `COMMIT` inside it, `ROLLBACK` under
  `suppress(sqlite3.Error)`. The observation store's deferred `BEGIN` becomes `BEGIN IMMEDIATE`, its first statement
  a write; the migrations' block and the catalog copier's per-source copy keep their own transactions, whose
  contracts differ.

### Lot 4b

(Corrected: rewritten by the re-cut of 2026-11-11, each block with its first `src` user, since vulture, run on `src`
alone, refuses a class, method or enum member no production code reaches. The choices the first table left open
are settled under "Lot 4b, settled at its start", below.)

- **Block 10**: the composition resolves the node id right after the node id store opens, before the webui and the
  graph, and gives it to every application step at its construction (the catalog steps, the search steps, the
  download steps, the status loop); the lifecycle loses its resolution step and its `NodeLoop`. The stores keep the
  id where it is the value written or a query key over catalog.db, which holds every node's rows
  (`NodeIdWriter.record_node_id`, `SourcePointReader`'s three reads). Past the file bound, accepted by the operator.
- **Block 20**: `domain/health/`, pure (no I/O, the clock injected), in `p2pwatch.domain`'s one tach module:
  `DeclaredFailure` at the domain's root; the reading's reason `ClientNotAnswering`, never raised; `Outcome`;
  `Health` (unknown, healthy, failing); `HealthCondition`, the source it reads, its failing band's entry and exit,
  unknown until its window fills; `HealthTransition`; `Component`, its labels, its conditions and their windows,
  without dependencies and without an aggregate health (lot 4c's). `HealthRecorder` in `application/steps/`, every
  outcome recorded through it on one component by one source, its subscribers awaited in order, each transition
  written in one log line; `HealthEventTranslator`, the subscriber turning the transitions into today's events. The
  status loop records its API reading on the client's component. The condition's tests include section 4's pattern.
  Past both bounds, accepted by the operator.
- **Block 25**: the degraded band and `Health.DEGRADED`; one component per channel, built by the composition after
  the client opens; "not connected" (failing at 6 of 6) and "not connectable" (degraded at 6 of 6), their reasons
  `ChannelNotConnected` and `ChannelNotConnectable`, each reading its own field; the channel timers replaced,
  `_AlertTimer` removed. If it passes a bound, it splits by field, "not connected" then "not connectable".
- **Blocks 30 to 38, the supervisor's preparation then its swap**, behaviour unchanged throughout. Each work waits
  before its turn, the first one included, its wait computed from its own state:
  - 30: `LoopSupervisor` renamed `Supervisor`, one supervising class from then on; `Work`, an ABC with `run_once()`,
    `wait_for_next_turn()` and a concrete `run()` (its wait, its turn, a yield, again), which block 38 moves into the
    supervisor; the status reading the first work, its wait the period left since its last reading, none at first;
    `docs/contributing/architecture.md` updated;
  - 33: download tracking (snapshot, tracker, decider, starter) as a work, its wait none at first, then the poll or
    the wake; `DownloadLoop` removed, `architecture.md` updated;
  - 34: source tracking out of the cycle, a work of its own reading the client's list, its turns `sources_interval`
    apart from start to start, as today; a `StoreError` of its reads logged as today until block 40;
  - 36: one work per (client, channel, keyword), enumerated by the composition, its wait `time_until_ready`, so a
    persisted backoff delays the first search after a start as today; `BackoffSaver`, the object the search works
    share, taking its snapshot at the first turn (after the lifecycle's `resume_waits`) and saving after each turn;
    `SearchTaskRunner` removed, `architecture.md` updated;
  - 38: the turn loop moves from `Work.run()` into the supervisor, which arms the bound and cancels every work at the
    shutdown; an exception still ends the node, as today, until block 40.
- **Block 40**: each turn's outcome: a declared failure logged in one line, a `Bug` with its trace, the turn alone
  failing; the floor after a `Bug`; every failure a driven port declares re-based on `DeclaredFailure` (D3); the
  status work lets `ClientAuthError` through, source tracking its `StoreError`; the search worker raises
  `SearchFailedError` and `ClientUnreachableError` after the backoff and its events, `BackoffSaver` saving in a
  `finally`. If it passes a bound: 40 the outcomes and the status work, 41 the search worker raising.
- **Block 45**: a request's total bound in the amuleapi adapter, 60 s, its expiry a `ClientUnreachableError` (httpx
  bounds each phase, never the whole request, so a server trickling its bytes kept a call alive past every limit,
  D6). (Corrected: the first starts' spacing is block 46's.)
- **Block 46** (Corrected: added on 2026-11-12, by block 45's class 2 question): each client's latest search starts,
  kept in `local.db` as the starts of persisted waits whose duration is the adapter's spacing, so a client built
  anew, by a restart of its owner or at the process's start, spaces its first starts from the previous ones by its
  network's rule, and waits for nothing when no start is due.
  - **Generic over networks and clients**, since multi network stage 5 adds clients: a row holds a client's name, a
    channel, a scope its adapter chooses within the channel (`''` for a channel-wide spacing, as eD2k's lock; the Kad
    word for Kad; its own for a later network), so no scope of one channel collides with another channel's, and the
    start's instant in micros. The spacing's value stays each adapter's constant, a network rule and never a setting
    (`agents/specs/2026-10-23-crawler-design-fixes.md`, its D8).
  - **The shapes**: `LatestSearchStart` in `domain/search/` (`channel`, `scope` a `str`, `started_at`); the
    `SearchStartWriter` and `SearchStartReader` pair, `set_latest_start(client_name, *, start: LatestSearchStart)`
    replacing the row of the same client, channel and scope, and `read_latest_starts(client_name)` returning a
    tuple; their `SearchStartStoreContract`; `FakeSearchStartStore`; `SqliteSearchStartStore` over `local.db`'s
    migration 0016, `latest_search_starts (client_name TEXT NOT NULL, channel TEXT NOT NULL, scope TEXT NOT NULL,
    started_at_micros INTEGER NOT NULL, PRIMARY KEY (client_name, channel, scope)) STRICT`, the opener's tests
    gaining its version and its table.
  - **The wiring**: the composition gives each client it builds its name, `WallClock`, and the one store as both
    ports, as it gives `MonotonicClock`; `tach.toml` gains the amuleapi adapter's dependency on the wall clock port
    and on the pair, and the composition's and `persistence_sqlite`'s entries on the pair; `.claude/rules/stores.md`
    names `WallClock` among the clocks the amuleapi adapter holds; `docs/contributing/architecture.md` its
    `local.db` tables and schema version.
  - **What is written**: the start's own instant, as the start is reserved: eD2k's `wall_clock.now()` when it takes
    its next start under the lock, before the search is posted; a Kad slot as `wall_clock.now() + (slot -
    monotonic_clock.now())`, the slot lying ahead when two keywords share a Kad word; a keyword without a Kad word,
    which spaces no network start, nothing. A failed post or a held Kad word spends its spacing, as today. The read,
    once at the client's construction, turns each row into its next allowed start through `remaining_wait`, so a
    wall clock stepped back never lengthens a wait past one spacing. A write is synchronous on the loop, as the
    backoff's: a few milliseconds (median 1.3 ms, max 2.2 ms over 300 `BEGIN IMMEDIATE` writes in WAL with
    `synchronous=FULL`, measured 2026-11-12 by the spec's review; the backoff ports' docstrings say under a
    millisecond, corrected when a block touches them).
  - **What is kept**: a scope no longer searched keeps its row, the table bounded by the client names, channels and
    Kad words ever configured. A `StoreError` on the read is logged and the client starts as today, without the
    earlier starts, where the backoff's read lets it through: a spacing lost costs one early start, a backoff lost a
    burst of refused searches. On the write it is logged and the search goes on, as the backoff's save (D2).
  - **The wiring test that restarts the node three times on one `local.db`**
    (`test_a_restart_re_evaluates_the_catalogue_only_once_a_policy_file_changed`) deletes the starts' rows between
    its runs, as it already writes `local.db` between them, since each run must read a search within 10 s.
  - The glossary gains `latest search start`, its scope included. `docs/migration-4x.md` is lot 7's: the new table is
    listed in section 6, "For lot 7".
  - Past both bounds (about 700 lines, 28 files, `.reviews/v5-lot4b-block-46-estimate.md`'s rows recounted by the
    spec's review), accepted by the operator on 2026-11-12: no cut leaves each part under both bounds with a production user,
    the eD2k-then-Kad cut leaving its first part at about 570 lines and 24 files.
- **Block 47**: each work's time limit, the turn raced against `MonotonicClock.sleep` with
  `asyncio.wait(FIRST_COMPLETED)`, as `download_loop.py` does, a turn past it a `TurnPastItsLimit`, recorded as a
  `Bug`. (Corrected: the race in a `TaskGroup` whose expiry task cancels the turn, which runs in the task that
  waited for it: a turn in a task of its own started one loop iteration after its wait, so a search could start on a
  backoff another work set in between, which two tests of `test_keyword_search.py` caught; the race's end suspends
  every turn, so the yield after it is removed.) Each limit is the sum of the bounds on its turn's path, measured on `efba50c5` (`S` the 60 s start spacing,
  `B` the 120 s search budget, `N` `notification_timeout_seconds`, `K` the deduplicated keywords, `K_w` those
  sharing one Kad word, `c` one amuleapi call: a login, the request, a re-login and a resend on a 401, so four
  requests under block 45's bound and two waits on the login lock), plus a fixed allowance of 5 minutes for what
  grows with live counts no setting bounds (section 6):
  - the status reading: `2c + 5N`;
  - an eD2k search: `(K-1)·max(S, B+2c) + S + B + 2c`, every keyword's turn waiting through the others' on the
    client's eD2k lock; a Kad search: `K_w·S + 2B + 3c`; (Corrected: `S + B + 3c` and `2B + 4c`, the answer's first
    page read after the eD2k lock, a Kad widening before each poll's sleep);
  - download tracking and source tracking: `2c + N` each, one page of each list and one notification, the allowance
    covering the other pages, the starts of unlisted downloads, the sources and their notifications;
  - the webui's liveness turn: the allowance alone, no await in it.
- **Block 50**: the default bands and how two bands combine, section 4's pattern tested again with both bands; the
  bugs condition, reading `TURNS`; every work's component (the status sensor, each keyword search, each channel's
  bugs condition, download tracking, source tracking); the supervisor recording each turn's outcome on the
  components its work feeds. The log line of block 20 is its first reader. If it passes a bound, download and source
  tracking's components move to block 51.
- **Block 51**: a channel's "searches failed", reading the search turns' declared outcomes and counting
  `SearchFailedError` alone; download tracking's "the client connected to no network", recorded by the status
  reading; the log line their first reader.
- **Block 52**: the `StateOwner` port, its `StateOwnerContract` and fake; `RestartPolicy` subscribed to the recorder;
  the restart in a task of the supervisor, the old works cancelled and awaited first, the bugs windows emptied;
  `AmuleClientOwner` in its own composition module, rebuilding every object holding the client, the composition
  naming each component's owner, the resource stack closing the current instance; the useless restarts counted, none
  past three, the count reset when every bugs condition of the owner's components is healthy again; a rebuild that
  raises records a `Bug` on each of the owner's components and is tried again after the floor, each failure counted
  useless. Past the line bound, accepted by the operator (draft 2's 42, 44 and 45 merged, so no block restarts
  without its limit).
- **Block 60**: the free-space reading recorded on download tracking, its reason carrying `free_bytes` and
  `min_free_bytes`, its condition entering at 1 of 1 and leaving at the first good reading, today's; `DiskSpaceLow`
  from the translator; `EdgeState` deleted, its only user gone.
- **Blocks 65, 68**: `WebuiLiveness`, a turn each status period (60 s) over what the webui thread exposes (through a
  callback the composition passes, the webui adapter depending on driving ports and the domain only), its component
  and bugs condition; the restart policy logging a failing component without an owner, its first case; then the
  webui thread's owner, rebuilt by the composition.
- **Blocks 70, 72, 74**: the dispatcher records each notification's outcome on one notifier component: a refusal
  the adapter's `NotificationRefused`, a send past `N` a `NotificationTimedOut`, both declared, any other exception
  a `Bug`, the bugs condition counting `Bug` alone; then the notifier's owner, the dispatcher holding the rebuilt
  notifier through one indirection; then the port listing its services and sending to one, one apprise object per
  URL, one component per service named by its scheme and its audience, never its URL, which carries the webhook's
  token, and its "sends refused" condition, the log line its first reader.
- **Block 90**: the handoff, `BACKLOG.md`'s sub-entry 4b deleted, the holistic review's fixes.
- **Glossary**: one line per D8 name and per new concept (`HealthRecorder`, `HealthEventTranslator`, `Bug`, the
  readings' reasons, the floor after a `Bug`, `BackoffSaver`, `WebuiLiveness`, `TURNS` and a condition's source), in
  the block that introduces it; the `declared failure` line covers the reasons never raised.

### Lot 4b, settled at its start

(Corrected: added by the re-cut of 2026-11-11.) From the lead's inventory of that day (the open choices of the first
table, read against the code at `efba50c5`) and the review of the corrected spec. Each answer is forced by the
decision or rule it names, the operator's, or the lead's where its row says so.

| Block | Choice | Answer | Why |
|---|---|---|---|
| 10 | how a step knows the node id | at its construction, the composition resolving it first | the operator, 2026-11-11 ("on uniformise avec les autres choses qui en avaient besoin"); a value the graph needs is resolved before it is composed (Seemann and van Deursen) |
| 10, 20, 52 | code written in one block for a user in the next | merged into one block, past the bound where the merge passes it | the operator, 2026-11-11 ("On fusionne les paires de blocs") |
| 20 | what a transition names | one condition of one component: the component, the condition, from, to | today's events are per field; an alert's key is a component and a condition |
| 20 | what publishes the transitions | one `HealthRecorder` every outcome goes through, calling its subscribers in order | the operator, 2026-11-11; Alertmanager's single fan-out |
| 20 | a reader of health in lot 4b | each transition written in one log line by the recorder | the operator, 2026-11-11: every condition then has a reader before the restarts, and the operator sees a part failing before lot 4c |
| 20, 25 | what a success counts for | every condition of its source, each condition its own window | the operator, 2026-11-11 (D10) |
| 20, 50 | how an outcome names its source | `record(outcome, on=component, by=source)`, each condition declaring the source it reads; a turn's outcome feeds the bugs conditions alone | the lead's, forced by the operator's answer on what a success counts for: one status reading judges two fields, a search turn feeds a keyword's component and its channel's |
| 20, 25, 60 | the data today's events carry | a declared reason carries its reading (`free_bytes`, `min_free_bytes`), a component its labels (`client_name`, `channel`) | the lead's: a transition names only its component and condition |
| 20 | which transitions emit today's events | entering a band emits the alert, only a return to healthy after it the end, unknown to healthy nothing | `_AlertTimer` sends a recovery only after an alert; D21, today's entry kept |
| 20, 25 | what an unknown reading records | nothing: the windows stay as they were while the client is unreachable | today only the API's own alert can fire then; a failure would alert every channel, a success heal them, and an emptied window would send a false end |
| 20, 25 | the duration the alert events carry | today's text, "for 2 min" and "for 5 min", derived from the entry band and the status period | D21 |
| 20 | the unreachable reading's reason | `ClientNotAnswering`, never raised, named apart from the event `ClientUnreachable` | every reading's reason the same shape; any `ClientError` counts, a refused route included |
| 20, 36, 65, 70 | the new concepts' names | `HealthRecorder` (Spring's `HealthContributorRegistry` names its peer), `HealthEventTranslator`, `ClientNotAnswering`, `BackoffSaver`, `WebuiLiveness`, `NotificationRefused`, `NotificationTimedOut`, `TurnPastItsLimit` | the lead's, by the Naming rules: the kind first, readable at a glance |
| 25, 50 | who builds the components | the composition, injected into every work and reading that records on them | D5's composition root |
| 30 | `Work`'s form | an ABC with `run_once()` and its wait before the next turn | the operator's answer on the wait (D4); `no-protocol-base.yml` |
| 30 to 38 | the order of the supervisor's blocks | the preparation (each loop a work, behaviour unchanged), then the swap, then the behaviour (block 40) | the operator, 2026-11-11, so no two supervisors run side by side (Beck: make the change easy, then make the easy change) |
| 30 | how a work runs before the swap | one concrete `Work.run()`, and `LoopSupervisor` renamed `Supervisor` | the lead's: one driving loop written once, not one per work, and one supervising class all along; block 38 moves the loop into the supervisor |
| 30 to 38 | the wait and the first turn | the wait before every turn, the first included, from the work's own state | today's order (`search_task_runner.py:64-66`): a backoff restored by `resume_waits` delays the first search |
| 30, 38 | the yield after a turn | kept, in the turn loop (Corrected: removed by block 47, the race's end suspending every turn) | a turn that never suspends must not starve the loop (`search_task_runner.py:70-71`) |
| 33, 34 | the download split | two works, each reading the client's list | the operator, 2026-11-11: a skipped sources round would count as a success, about ten per real round |
| 34 | source tracking's interval | start to start, as today | `source_watcher.py:85-91` |
| 36 | where the search works are enumerated | the composition (`dedupe_keywords`, `client.channels()`), the owner reusing it | D5, no factory leaves the composition root |
| 36, 40 | the backoff's save | `BackoffSaver`, its snapshot at the first turn, a save after each turn, in a `finally` once the worker raises; its `StoreError` logged as today, never the outcome | D2: the outcome is the network's; a snapshot taken before `resume_waits` would rewrite what it read |
| 38 | the shutdown | the supervisor arms the bound, then cancels every work, a restart in flight included | lot 4a's bounded shutdown |
| 40 | which failures are re-based on `DeclaredFailure` | every failure a driven port declares | the operator, 2026-11-11, D3 whole: one rule, a new port's failure following it |
| 40 | `ClientAuthError` | re-based with `ClientError`: a password refused while running is a declared outcome, the node running, its condition lot 4c's block 73 | the lead's, by D5: three restarts cannot repair a configuration; no release between the two lots |
| 40 | after a `Bug` | the next turn waits at least a floor, 60 s, the later of the floor and the work's own wait, never their sum | the lead's: without it a bug before the client's pacing reruns at full speed, a trace per turn (Kubernetes' CrashLoopBackOff); 60 s is the client's own start spacing, a starting value tuned at the release candidate |
| 40 | a failed search | raised after the backoff and the events | recorded as a success, a declared failure would break the bugs window's streak |
| 45 | a request's total duration | 60 s in the amuleapi adapter, its expiry a `ClientUnreachableError` | the lead's: httpx bounds each phase only (D6); six times the per-phase 10 s, so a page answering within its phases never meets it |
| 46 | a client built anew | its first starts spaced from its latest ones, persisted in `local.db`, after a restart of its owner and at the process's start (Corrected: the lead's first answer, a minute's wait at every start, failed the wiring tests' real-clock bound) | the operator, 2026-11-12 ("stockant dans local.db la date et heure de dernier lancement ... Ça résoudrait les deux cas"): a new client forgets its last starts, and the spacing is the network's rule (`amule_api_client.py:60-62`) |
| 46 | what is written | the start's own instant, as it is reserved: eD2k's at its reservation under the lock, a Kad slot's converted to the wall clock; a keyword without a Kad word nothing | the lead's: behaviour as today, a failed post or a held Kad word still spacing the next start; writing the next start instead would wait up to two spacings, and the reservation's own instant would let a Kad word restart one second after a start |
| 46 | the row's key | the client's name, the channel, a scope within it | the lead's, to meet the operator's "ça doit être générique pour généraliser ça à d'autres réseaux p2p ... et donc clients" (2026-11-12): the core knows no network's pacing, each adapter names its scopes; a Kad word may be spelt `ed2k`, so a single key would collide; by client as the backoff's rows, since an eD2k server counts two clients of one address apart, the operator's account of 2026-11-12 ("2 clients sur la même IP ... sont comptés différemment, mais un 3e compte comme un acteur malicieux"), so two clients never share a spacing |
| 46 | a `StoreError` on the starts | logged; on the read the client starts as today, on the write the search goes on | the lead's: a store failure never fails the network's work (D2); the read departs from the backoff's, which lets it through, since a spacing lost costs one early start and a backoff lost a burst of refused searches |
| 47 | each work's time limit | the sum of the bounds on its turn's path, plus a fixed allowance of 5 minutes for the live counts | a limit under that sum cuts a healthy turn as a `Bug`; the turns growing with the tracked downloads, their sources and the files of an answer stay under a per-turn limit, the operator's answer of 2026-11-11 ("sur un crawler à la recherche de lost media le nombre de téléchargements est par définition faible"); the allowance's value the lead's |
| 47 | the turn's timeout | raced against `MonotonicClock.sleep`, the loser cancelled | the lead's: `asyncio.timeout` is refused in the core (`core-import-names.yml:28`), and the race needs no new port operation |
| 50 | how two bands combine | while failing holds, degraded is not held; on leaving failing, degraded enters only by its own entry | section 4's pattern ends healthy, which two independent latches do not |
| 51, 74 | "searches failed", "connected to no network", a service's "sends refused" | in lot 4b, the log line their first reader | the operator, 2026-11-11 |
| 52 | which task runs a restart | a task of the supervisor, never the turn whose outcome triggered it | the restart cancels the works relying on the owner, that turn among them (OTP: the supervisor restarts, not the child) |
| 52 | who cancels the old works | the supervisor, awaiting them before `restart()`, which adds the new ones | OTP: the supervisor terminates its children before restarting them; a call in flight on a closed client raises |
| 52 | which windows a restart empties | the bugs conditions' only | D10, the policy reads the bugs condition alone; a sensor window emptied would lose an open alert's end or send it twice |
| 52 | a rebuild that raises | a `Bug` on each of the owner's components, tried again after the floor, counted useless, three at most | the operator, 2026-11-11: the components show failing; retrying for ever would repeat refused logins, which amuleapi answers by locking the address out |
| 52 | when the count resets | when every bugs condition of the owner's components is healthy again | the lead's: the owner is then repaired, and a second bug elsewhere in it counts against the same restarts |
| 52 | the limit with the restarts | in the same block | the lead's: a block restarting without its limit would restart a deterministic bug's client every three bugs |
| 52 | `StateOwner`'s surface | a port file with its tach entry and a `StateOwnerContract` each owner and its fake subclass | `.claude/CLAUDE.md`, a contract per contracted port |
| 52 | what the client's owner rebuilds | every object holding the client (`SearchWorker`, `StatusLoop`, `DownloadCycle`, `DownloadStarter`, `SourceWatcher`); the tracker's loss deadlines, the backoff and the cataloguer kept | D5 clears the owner's memory, not the steps' |
| 52 | what the resource stack closes | the owner's current instance | the stack registers the first one: the live session would never log out |
| 52, 65, 68, 72 | how the policy finds an owner | the composition names each component's owner; a failing component without one is only logged (from block 65, the webui's before 68) | one mapping for every owner, the notifier included, which feeds no work |
| 60 | the disk condition | enters at 1 of 1 and leaves at the first good reading | D21 over D9's single failure (D9's mark): today's `EdgeState` re-arms at the first good reading, so a second dip alerts again |
| 65 | the webui's turn | a liveness turn each status period (60 s), a fallen thread a `Bug` | D4: a turn that serves until the thread falls has no limit, and no asyncio cancellation reaches a thread (Kubernetes' liveness probe); the period the lead's |
| 65 | where the webui's work lives | the composition or a core step over a callback, never the webui adapter | the webui adapter depends on driving ports and the domain only (`tach.toml`) |
| 70 | a notification's outcome | a refusal `NotificationRefused`, a send past `N` `NotificationTimedOut`, both declared; any other exception a `Bug` | the lead's, by D3: a slow service is the network's, not a bug, and must not restart the notifier |
| 74 | a service component's name | its scheme and its audience, never its URL | a URL carries the webhook's token, and lot 4c exports component names |

### Lot 4c

- **Blocks 05, 07** (Corrected: moved from lot 4b by its re-cut of 2026-11-11): `Dependency`, `Quorum.ALL` and
  the propagation, `Component`'s health the worst of its conditions and of what its dependencies give it, the `all`
  edges of today's node, with the health gauge (one series per component and state, as resilience4j exposes a
  breaker's state), moved from block 30, as their first reader, through a subscriber of the recorder; the databases'
  edges join at block 76; then the `ANY` and `NONE` quorums and the rest of today's
  graph, read by the same gauge, and a test of the graph's shape. Split for the bound.
- **Blocks 10, 15, 18**: (Corrected: block 10 also builds the root causes and their impact, moved from lot 4b, the
  alert opening their first reader) `HealthAlert` and the grouping in the domain; the five events `ChannelDegraded`,
  `ChannelRecovered`, `ClientUnreachableLasting`, `ClientReachableAgain`, `DiskSpaceLow` replaced; the apprise texts.
- **Blocks 20, 25**: a `local.db` migration for the open alerts (component, condition, reason, severity, opened at), its
  port pair, store, contract and fake; at the start, the open alerts are loaded, those of a component absent from the
  graph closed, the others held until their condition is known; "node online" lists them.
- **Blocks 30, 35** (Corrected: the gauge moved to block 05; if block 10 splits for the bound, 30 and 35 merge): a
  counter of outcomes per component and reason, labelled by client, channel and keyword where they
  apply; `p2pwatch_crawler_up` removed; the fixtures of the old Prometheus text updated.
- **Block 40**: the Node page lists every component, its health, its reason and since when.
- **Blocks 50, 55**: the MicroProfile paths and JSON; the event loop's heartbeat, a monotonic instant the webui thread
  reads; the compose healthcheck on live.
- **Block 60**: `faulthandler.dump_traceback_later(timeout, exit=True)` armed once the graph runs and re-armed at each
  beat; its timeout a constant.
- **Blocks 70, 73, 76**: `MigrationError` and `PersistenceError` at start refused in one line by the command line; the
  status sensor no longer re-raises `ClientAuthError` (Corrected: a declared outcome under the supervisor since lot
  4b's block 40, this block adding its condition), the startup open tolerates it, the client's password condition
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
| Kad bug | the umbrella's probe `test_a_kad_bug_stops_the_working_ed2k_tasks_too`, inverted; fails if the eD2k searches stop (Corrected: Kad's failing and the roles' degraded health checked in 4c's block 07) |
| One keyword's bug | a supervisor test with two keywords, one raising at every search; fails if the other keyword's searches stop, or if the client is restarted more than three times |
| `time_limit` | a unit whose `run_once` never returns; fails if no `Bug` outcome is recorded within its timeout |
| Restart policy | a component failing on bugs with no recovery; fails unless exactly three restarts of its owner happen, then none |
| aMule unreachable (4b) | a graph test; fails if any owner is restarted or if the channels are not failing (Corrected: in 4b a status loop and restart policy test, failing if any owner is restarted or the client's unreachable condition is not failing; the channels' propagation is 4c's, its graph test at block 07) |
| `000111000111` | a condition test feeding the pattern ten times, then ten successes; fails if the condition is not failing from the first period's third failure, leaves failing during the pattern, or is not healthy after the successes |
| Connectivity alerts in 4b | the status loop's tests, their ends updated to the hysteresis; fail if an event is not emitted at today's entry |
| Two status fields (Corrected: added 2026-11-11) | a status loop test, Kad not connectable and connected reading after reading; fails if `ChannelDegraded(connectable)` is not sent at the sixth reading, or if a not connected alert is sent |
| Unknown reading (Corrected: added 2026-11-11) | a status loop test, failed readings, one unreachable reading, then at least six failed readings again; fails on an end or a second alert |
| Restart under an open alert (Corrected: added 2026-11-11) | a restart policy test restarting the client while a channel's alert is open, then at least six failed readings; fails on a second alert or an end |
| Floor after a `Bug` (Corrected: added 2026-11-11) | a supervisor test whose work raises at once; fails if two turns start closer than the floor |
| Raising rebuild (Corrected: added 2026-11-11) | a restart policy test whose owner's `restart()` raises twice, then succeeds; fails on a stop, if the owner's components are not failing between the attempts, if two attempts start closer than the floor, or if the works do not run again after the third |
| Password refused while running (Corrected: added 2026-11-11) | a supervisor test whose client raises `ClientAuthError` at every call; fails on an `ExceptionGroup`, or if a turn records anything but a declared outcome |
| Persisted starts (Corrected: added 2026-11-12) | adapter tests: a client building over a store holding a start 20 s old, then one 70 s old, fails if its first start does not wait 40 s, or if it waits after the 70 s one; a client starting a search, then a second built over the same store, fails if the second's first start on that channel and scope does not wait the spacing minus the elapsed time, run for eD2k and for one Kad word sharing its slot with a second keyword; a stored start ahead of the wall clock fails if it waits past one spacing |
| Persisted backoff at start (Corrected: added 2026-11-11) | a search work test with a backoff restored by `resume_waits`; fails if the first search starts before the persisted wait ends |
| Time limits (Corrected: added 2026-11-11) | a supervisor test with ten eD2k keywords queued on the real adapter's lock over `FakeAmuleApiServer`, each search held for its budget; fails on any `Bug` |
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

(Corrected: the last sentence is the first table's; lot 4b's re-cut of 2026-11-11 measured below.)

**Lot 4b's re-cut** (Sonnet, three passes on 2026-11-11, on `main` at `efba50c5`, estimated on code not yet written,
ranges, `.reviews/v5-lot4b-recut-estimate-3.md` the last, adjusted by the review's corrections): 21 blocks, the
closing one included (Corrected: 22 rows with block 46 of 2026-11-12, and the splits of 25, 33 and 40 made in Act,
which the closing block records). Past a bound and accepted by the operator: 10 (340 to 470 lines, 26 to 28 files), 20
(660 to 900, 21 to 26), 52 (710 to 990, 20 to 27, the limit merged in); 46 (about 700 lines, 28 files) accepted by the
operator on 2026-11-12. Near a bound, re-measured at their start, each with its
lever: 25 (350 to 520: by field), 36 (350 to 540: the enumeration first), 40 (450 to 660, 17 to 22 files, every
port's failure re-based: the search worker's raising apart, as 41), 47 (250 to 400), 50 (380 to 600, 14 to 19 files:
the download components to 51), 74 (300 to 420, 10 to 13 files). The others under 460 lines. The review's recount of the
third estimate's rows, about 5 850 to 8 790 lines before its corrections, against about 3 200 to 5 100 for lot 4b's content on
2026-11-09, the graph and the root causes excluded: the node id at construction, the two download works, the derived
time limits and the request's bound were added by the choices of 2026-11-11, the rest by what the sketch did not
show.

**Lot 4c with the moved pieces**: 05 (450 to 650), 07 (300 to 420), 10 grown by the root causes (450 to 650, its
lever 10a the root causes and the opening, 10b the impact in the message), 30 shrunk to the outcome counter (200 to
280), 76 grown by the databases' edges (30 to 50 lines): 18 blocks, 30 and 35 merging if 10 splits.

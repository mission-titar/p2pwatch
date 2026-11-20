# v5 lot 4b6: the health model redrawn

Tier Spec. This spec redraws part of the model of `agents/specs/2026-11-15-v5-lot-4b-health-model.md` (the lot 4b
spec): its D1, D4, D6 and D14 to D16 are replaced by the decisions below, and its D18 gains the word "outage"; its
other decisions stand. Lot 4c is rewritten on this spec's names once this lot has merged.

Why: reading lot 4b5's stack (#791, #798, 2026-11-18), the operator found the objects around the restarts and the
alerts hard to follow, and the model mixed two causes: a bug of our code, and an outage of something outside the
program. Every decision below was settled with the operator in that review, on 2026-11-18. The stack's last three
pull requests, #798, #799 and #801, which began them, were closed unmerged; #801 is read as a draft of blocks 30
and 35.

## 1. In short

A bug is our code's: the supervisor counts the bugs of each object it can rebuild (the aMule client, the webui, the
notifier) and rebuilds the object whose bugs keep coming back, waiting longer each time. When three rebuilds repair
nothing, the cause lies in something shared, so the crawler stops and Docker starts it again, whole; this goes on
without end, slowly, an alert at each round.

An outage is outside the program: amuled silent, Kad off its network, the disk full, Discord refusing, a refused
password. What can have one is an external dependency, and each of its rules carries the alert it sends, or none. The
node's health tracks the outages alone.

Every notification goes through one outbox: a turn leaves its notification there and ends, a work of the notifier
sends it. The outbox lives in memory and is saved in `local.db` at each change, so a notification survives a restart
of the node; a save that fails is an outage of the local database, with its alert.

## 2. What the operator will see

- **A bug rebuilds, an outage alerts**: no log line says a channel has bugs any more; a bug names the object it
  rebuilds.
- **An object whose bugs repeat is rebuilt after 1, then 2, then 4 minutes**; the third rebuild in vain sends an alert
  and the crawler restarts, amuled untouched. A node that keeps failing so restarts every 7 minutes and its start at
  least.
- **A refused password calls the operator**: an alert at the start, at a rebuild or while the node runs, the node
  running and logging in again every 30 minutes at most. It no longer stops the node at its start.
- **A notification already decided survives a restart of the node**; one may be sent twice when the node stops in the
  middle of its send.
- **A local database that cannot be written alerts**: the notifications still go out, and the alert says they would be
  lost at the next restart.
- **Today's alerts are unchanged**: their text, their start and their end.

## 3. Decisions

### Two causes

- **D20. A bug is a fault of our code; an outage is something failing outside the program. A bug is the
  supervisor's, which rebuilds; an outage is the node's health's, which alerts the operator.** *Two causes call two
  answers. Recorded together, a bug in a Kad search read as `channel amuled kad, bugs: healthy to failing`, as if Kad
  had the bug.*
- **D21. A known error is repaired where it is seen when that code can repair it; it is an outage when nothing in the
  program can; it is left to rise as a bug when only a rebuild repairs it.** The expired session is the first case
  (the client logs in again on a 401), aMule off the second, a state in memory gone wrong the third. *An error is
  handled at the lowest level that knows how, and nowhere else (Armstrong): the supervisor tells only an expected
  error from a bug, coupled to no part of the program.*

### Outages

- **D22. What can have an outage is an external dependency: amuled, each of its channels, the download disk, the
  local database and each notification service. Each of its rules carries the alert it sends, or none.** Download
  tracking is no longer one: "disk space low" goes to the download disk, "connected to no network" to amuled. The
  webui has none: its thread ending is a bug. *A "component" reads as an object of the program, as in Spring, where
  these are things the node depends on without controlling them (the SRE book's dependencies). Built together, an
  alert without a rule cannot exist, and a rule without an alert says so.*
- **D23. The node's health tracks the outages alone: it logs each change and dispatches its alert, as every other
  event is dispatched.** *The alerts are its only reader once the bugs are the supervisor's; with the sends recorded
  by the notifier's work, the dispatcher no longer needs the node's health, and the cycle that needed a subscriber
  plugged in later ends.*
- **D24. A refused password is an outage of amuled, with its alert: at the node's start, at a rebuild of the client,
  or at a turn. The node never stops nor restarts for it; the client logs in again after 1 minute, then twice as long
  each time, 30 minutes at most.** *A restart repairs no configuration: the operator must be called, and a node
  stopping at its start on it would loop under Docker. One login a minute at most stays under amuleapi's lockout (5
  refused logins in 60 s); 30 minutes bounds how long a corrected password waits.* It was lot 4c's.

### Bugs and rebuilds

- **D25. The supervisor counts the bugs of each object it can rebuild, over every turn of the object's works: failing
  at 3 in a row, healthy again under 2 in the last 10. A rebuild forgets them.** *The object is what a rebuild renews.
  A bug that comes back on one keyword alone, between healthy turns of the others, rebuilds nothing, which is right: a
  bug that repeats identically is in the code, and no rebuild fixes it; each one keeps its line and its trace.*
- **D26. The supervisor alone decides each rebuild and runs it: it stops the object's works, closes the object, has
  its builder build a new one and runs that one's works, after 1, then 2, then 4 minutes. A rebuild is in vain when
  the object's bugs turn failing again before they are healthy, or when it raises; the count resets once they are
  healthy.** *An OTP supervisor holds both the strategy and its bound; the restart policy, its request, its runner and
  the subscriber plugged in later only joined two halves, which the node's health separated. The waits double, as
  every backoff the literature names does, and stop at the third, which D27 hands over.*
- **D27. At the third rebuild in vain, an alert is dispatched, and the crawler stops with an error, which says why
  it stopped; Docker starts it again, whole; without end.** *A cause in something shared (the database connections,
  the matching engine) is renewed only with the whole process. The literature never gives up and never loops fast: it
  waits longer, then calls a human (Kubernetes' `CrashLoopBackOff`, the SRE book). D26's waits hold the pace in
  memory, so nothing persisted holds it, since a broken database would break it too. Docker's `on-failure:3` never
  resets its count and restarts nothing after a reboot (appendix C).*

### Notifications

- **D28. Every notification goes through one outbox, in memory: a turn leaves it there, without awaiting anything,
  and ends; a work of the notifier sends it, one entry per notification and service, removed once its send has ended:
  sent, refused, past its timeout or met a bug; a send cancelled, by a rebuild or the shutdown, keeps its entry.** *One way, safe by its design: nothing awaited between a decision and its entry, no
  cut turn and no rebuild loses it, so the shielded sends, the dispatcher's check of a notifier rebuilt meanwhile and
  the notification timeout in the turns' time limits all go. An entry kept after a bug would rebuild the notifier, then
  restart the node, without end.*
- **D29. The outbox is saved in `local.db` at each change and read back at the start; a save that fails is an outage
  of the local database, which the notifier's work records at each turn, its alert going out from memory. At the shutdown, the outbox is emptied within the shutdown
  bound.** *Sending from memory keeps one way to send whatever the database; saving lets a notification survive a
  restart, sent at least once, twice when the node stops in the middle of its send. Emptied at the shutdown, D27's
  alert goes out even when `local.db` cannot be written. The outbox keeps the end of its latest save and records
  nothing itself, so it needs no node's health and leaves no cycle.*
- **D30. A refused send is tried once, as today.** *Retried, a removed webhook would be retried without end, and would
  need a rule to give up.*

### How the lot is cut

- **D31. Lot 4b6 is one stack of its own, with its closing block, its holistic review, its handoff and a reading
  guide at the head of its first pull request.** *The operator reads and merges it whole before lot 4c is rewritten on
  its names.*

## 4. Acceptance

Commands and the output that fails each row: appendix B.

### Bugs and rebuilds

| Check | After the lot | On `main` |
|---|---|---|
| A bug at every turn of the client's works | the client rebuilt after 1, 2, then 4 min, then an alert and the crawler exiting with an error | rebuilt three times in vain, then never again |
| A bug at every turn of one keyword's search, the others healthy | nothing rebuilt, each bug logged with its trace | the client rebuilt three times, that search's bugs rule failing |
| After two rebuilds in vain, ten healthy turns, then bugs again | rebuilt after 1 min, the count back at zero | the count reset by the parts' bugs rules |
| The webui's thread dying | the webui rebuilt and serving again | the same |
| A bug at every send of the notifier | the notifier rebuilt after 1, 2, then 4 min, then the crawler restarting | the notifier rebuilt three times in vain, then never again |
| A bug in a Kad search | no `channel amuled kad, bugs` line | `channel amuled kad, bugs: unknown to failing` |

### Outages

| Check | After the lot | On `main` |
|---|---|---|
| A refused password at the start | the node running, the password alert sent, one login a minute at most | the crawler stops, at every start |
| A refused password while running | the password alert, the node running | an expected error each turn, no alert |
| The password right again | the password alert's end | n/a |
| aMule connected to no network | amuled's "connected to no network" rule failing, in the log | download tracking's rule failing |
| One notification service refusing every send | its "sends failed" rule failing, in the log, no alert | the same |

### Notifications

| Check | After the lot | On `main` |
|---|---|---|
| A notification decided, the crawler stopped before its send | sent after the restart | lost |
| A decision's write and its notification | no suspension between the two | an awaited, shielded send |
| `local.db` refusing every write | every notification sent, the local database's alert | every notification sent, no alert |
| The third rebuild in vain, `local.db` refusing every write | its alert sent before the crawler exits | n/a |
| Two services, one refusing | the other sent once, the refused one not tried again | the same |

### What must not change

| Check | Observed by |
|---|---|
| The lot 4b spec's "What must not change" table | each of its rows, as that spec observes it |
| Today's alerts | a test written in block 5, against `main`: each alert's planned log line, severity and notification, and the reading it starts and ends at, the same at the lot's end |
| aMule unreachable | nothing rebuilt, the unreachable alert |

## 5. Blocks

One stack from `main`, its blocks numbered by fives; each block's size is estimated against its parent (appendix C).

| Block | Branch | Content | Estimated size |
|---|---|---|---|
| 5 | `test/todays-alerts-held` | today's alerts held by a test | 221 lines, 3 files (Corrected: cut out of block 10, which came to 663 lines, the lead on 2026-11-18) |
| 10 | `refactor/external-dependencies` | the component renamed an external dependency | ~250 lines, ~30 files, past the file bound (Corrected: 448 lines, 51 files, its parameters, attributes and locals uncounted by the estimate) |
| 13 | `test/steps-read-handed-on-notifications` | the steps' tests read the notifications their dispatcher hands on | 46 lines, 10 files (Corrected: cut out of block 15, the lead on 2026-11-18) |
| 15 | `refactor/notifications-through-the-outbox` | the outbox in memory, the notifier's work sending from it | ~700 lines, ~13 files, past the line bound (Corrected: 1 542 lines, 31 files, the dispatcher's send tests moving to the notifier's work and every test building a dispatcher uncounted by the estimate, accepted by the operator on 2026-11-18) |
| 20 | `refactor/shielded-sends-removed` | the shielded sends and the notification timeout in the turns' limits removed | ~350 lines, ~14 files (Corrected: 213 lines, 18 files, the shielded sends alone) |
| 23 | `refactor/no-notification-timeout-in-time-limits` | the notification timeout in the turns' limits removed | 37 lines, 7 files (Corrected: cut out of block 20, which came to 25 files, the lead on 2026-11-18) |
| 25 | `feat/outbox-saved` | the outbox saved in `local.db`, the local database an outage | ~650 lines, ~14 files, past the line bound (Corrected: 913 lines, 22 files, the outbox saved and read back alone, past both bounds, accepted by the operator on 2026-11-19) |
| 27 | `feat/local-database-outage` | the local database an outage, with its alert | 249 lines, 18 files (Corrected: cut out of block 25, which came to 1 161 lines and 31 files) |
| 30 | `refactor/client-built-whole` | the aMule client built whole at each rebuild, the supervisor keeping one record per object | ~600 lines, ~14 files, past the line bound |
| 35 | `refactor/webui-and-notifier-built-whole` | the webui and the notifier built the same way | ~300 lines, ~6 files |
| 40 | `refactor/supervisor-counts-the-bugs` | the bugs counted per object and each rebuild decided by the supervisor; the restart policy and the bugs rule removed | ~1 200 lines (~700 removed), ~30 files, past both bounds |
| 45 | `feat/rebuild-waits` | the rebuilds after 1, 2, then 4 min | ~280 lines, ~4 files |
| 50 | `feat/crawler-restart-past-three` | the crawler stopped with an error at the third rebuild in vain, its alert | ~300 lines, ~16 files |
| 55 | `refactor/rules-carry-their-alerts` | each rule carrying its alert, download tracking split | ~350 lines, ~12 files |
| 60 | `feat/password-refused-outage` | the refused password an outage of amuled, with its alert | ~280 lines, ~6 files |
| 65 | `feat/login-tried-again` | the login tried again after waits that double | ~300 lines, ~6 files |
| 80 | `fix/lot-4b6-review-fixes` | the holistic review's fixes | |
| 90 | `docs/lot-4b6-wrap` | closing block | |

A block past a bound carries one piece with its first reader: 10 a rename; 15 the outbox with its writer, the dispatcher, and its reader, the notifier's work; 25 the store with its
reader, the outbox at the start; 30 the port, its contract and its fakes with the first object built through them; 40
is mostly removals, the restart policy and its tests, which nothing reads once the supervisor counts.

The order: the rename comes first, so every later block is written in the lot's words (the operator, 2026-11-18); the
price is that the four components holding the bugs rule alone (the webui, the status reading, each keyword search,
source tracking) are named external dependencies until block 40 removes them. The outbox comes next (blocks 15 to
25): with every notification sent by the notifier's work, nothing outside the supervisor reads the latest notifier, so
the objects built whole (blocks 30 and 35) need no handle on it, and when the supervisor counts the bugs (block 40), a
send is already a turn of that work.

## 6. Limits and scope

### Accepted limits

- **A node whose cause survives its own restart restarts every 7 minutes and its start, without end**, an alert at
  each round, until the operator steps in (the operator, 2026-11-18).
- **A notification can be sent twice** when the node stops between its send and the save of its removal.
- **A notification is lost when the process is killed** between a decision's write in `catalog.db` and the save of
  its entry, or before its save when `local.db` cannot be written.
- **A notification refused by its service, or whose send met a bug, is lost**, as a refused one is today.
- **A kept entry goes to the service that bears its name at the start**: two URLs of one scheme and audience swapped
  in the configuration between two runs swap their entries, both of the same audience.
- **When the notifier's bug survives the restart, its alerts never go out**: nothing else sends them; the log keeps
  them.
- **A rule that no code records stays unknown, and nothing says so**: each rule is recorded at one place, which that
  work's tests prove. A log line for a rule still unknown after a while was weighed and dropped: a community service
  a lost-media node seldom notifies stays unknown for days, healthy.

### Adjacent backlog items

- **Lot 4c**: its draft's D17 ("the crawler stops only when it cannot build its graph or the supervisor itself
  fails") is superseded by D27; its entry's "graph of parts" becomes the graph of dependencies.
- **Multi network, stage 5**: a free-space check per client's output directory meets the download disk as one
  dependency.

## Appendix A. Design

Every piece sits in its ring: the outbox and the supervisor's records are steps of `application/`, with no I/O; the
outbox's saving is a driven port pair, `NotificationOutboxWriter` and `NotificationOutboxReader`, implemented by one
SQLite adapter; the dependencies, their rules and their alerts are `domain/`; the composition alone wires them.

### Names

| Name | What it is | Example |
|---|---|---|
| `ExternalDependency` | something the node depends on and does not control, which can have an outage; replaces `Component` | `client amuled`; `channel amuled kad`; `download disk`; `local database`; `notifier discord community` |
| `HealthAlert` | the alert a rule of a dependency sends when it turns failing, and its end when it turns healthy again, or none | Kad's "off its network for 5 min", then "back on its network" |
| `NotificationOutbox` | the notifications left to send, in memory, one entry per notification and service | |
| `NotificationOutboxWriter`, `NotificationOutboxReader` | the outbox's save in `local.db`: `set_pending_notifications(entries)` replaces it, `read_pending_notifications()` reads it back | |
| `SupervisedObject` | the supervisor's record of one object it rebuilds, private to it: its builder, the latest object built, whether each of its latest turns met a bug (judged by `BUGS`' thresholds), its rebuilds in vain | the aMule client's record |
| `outage` | the glossary's word for something failing outside the program | aMule off, a refused password |

Removed: `Component`, `BUGS` as a rule of a dependency, `RestartPolicy`, `RestartRequest`, `RestartRunner`,
`node_restart_policy`, `HealthSubscriberBuiltLater`, `dispatch_shielded`, `finish_shielded_dispatches`,
`CurrentNotifier`'s check of a rebuilt notifier, `notification_timeout` in `AmuleWorkTimeLimits`, the components
that held `BUGS` alone (`status_reading_component`, `keyword_search_component`, `source_tracking_component`,
`webui_component`).

Each dependency keeps its name in the log (`client amuled`, `channel amuled kad`), but download tracking's, which
becomes `download disk`. Each block corrects the glossary lines and the paragraphs of
`docs/contributing/architecture.md` (§10.1, §10.2) and `domain/health/__init__.py` that it makes false.

### The model, as the code reads

```python
# domain: what can have an outage, each rule with its alert or none
kad = ExternalDependency(name="channel amuled kad", rules={
    CHANNEL_NOT_CONNECTED: HealthAlert(when_failing=ChannelDegraded(...), when_healthy_again=ChannelRecovered(...)),
    SEARCHES_FAILED: None,
})

# application: the status reading records an outage check
await node_health.record(on=kad, rule=CHANNEL_NOT_CONNECTED, detected=not status.kad.connected)
# node_health: logs the change, dispatches its alert; the dispatcher logs it and leaves it in the outbox

# application: the supervisor, once a turn has ended
self._objects[builder].record_turn(met_a_bug=met_a_bug)  # failing: rebuild after 1, 2, then 4 min
```

### Block 5, today's alerts held

- A test holding today's alerts against `main`: each alert's planned log line, severity and notification, the reading
  each starts and ends at; it stays unchanged to the lot's end.

### Block 10, external dependencies

- `Component` renamed `ExternalDependency` through Serena, the class and its `component` names; the glossary's
  `component` line becomes `external dependency`, `outage` added.

### Block 15, the outbox in memory

- `NotificationOutbox`, a step: `leave(notification, services)` adds one entry per service, synchronously, and wakes
  the notifier's work; `oldest()` and `remove(entry)`.
- The dispatcher plans, logs, writes the metrics, then leaves the notification, with no await before; its `_send`,
  `_send_to`, `CurrentNotifier`, its check of a notifier rebuilt meanwhile and its `notification_timeout_seconds` go.
- The notifier's work, handed back by the notifier's rebuild: each turn sends the oldest entry within
  `notification_timeout_seconds`, records "sends failed" on its service in the node's health, removes the entry once
  the send has ended (sent, refused, past its timeout, or met a bug, which is a bug of its turn, recorded on its
  service's bugs rule until block 40); a cancelled send keeps its entry. Its time limit: one send's timeout plus the
  margin. Its wait: until the outbox holds an entry.
- At the shutdown, the lifecycle sends what is left within the shutdown bound, then stops.
- The glossary gains `notification outbox` and the notifier's work.
- (Corrected: as built in block 15, 2026-11-18. The notifier's work is one work over every service, so a bug of a send
  is recorded on every service's bugs rule, the object's count of D25 a block early; its log line is the supervisor's
  `bug in notification sending`, refusals and timeouts keeping theirs. The shutdown's last sends go through a
  notifier the lifecycle builds at the start, nothing else holding the latest one from block 30. The outbox waits
  through the `Waker` port, `WakeSubject.NOTIFICATION`; an entry is a `PendingNotification`. With no service
  configured, the notifier hands back no work.)

### Blocks 20 and 23, the shielded sends removed

- 20: `dispatch_shielded` and its four callers (`download_tracker`, `file_judge`, `source_watcher`,
  `health_alerter`), `finish_shielded_dispatches` and its call in `crawler_lifecycle`. (Corrected: as built, the
  acceptance test covers the health alerter too, and its `call_soon` callback is scheduled before the step's call, so
  it proves no suspension from the turn's start to `leave`, which holds the spec's interval.)
- 23: `notification_timeout` in `AmuleWorkTimeLimits` and its two tests.

### Block 25, the outbox saved

- `NotificationOutboxWriter.set_pending_notifications(entries)` and `NotificationOutboxReader.read_pending_notifications()`;
  one adapter, `SqliteNotificationOutboxStore`, over a new `local.db` table, its migration and its line in
  `docs/migration-4x.md`; `NotificationOutboxStoreContract`, run by the SQLite store and the fake.
- The four kinds of notification kept in an entry: the relayed log line, the tier rise, the source alert, the completed
  download.
- The outbox saves itself at each change, keeps the end of its latest save, and reads itself back at the start; an
  entry whose service no longer exists in the configuration is dropped at the start, in one log line.
- 27 (Corrected: cut out of 25): the notifier's work records, at each turn, whether the outbox's latest save failed on
  the local database; the local database's dependency, rule and alert below. (Corrected: as built, the outbox reads
  itself back in its constructor, a failing read stopping the start as the backoff's does; each refused save logs one
  warning.)
- The local database: a dependency, its rule "saves failed" (failing at 3 in a row, healthy again under 2 in the last
  10, as "sends failed") with its alert, `operations` audience: "notifications not saved in local.db: lost at the next
  restart", its end "notifications saved again". The glossary gains `local database` and `saves failed`.

### Blocks 30 and 35, built whole

- Each restartable is built whole at each rebuild: `Restartable.works()` and `close()`, `RestartableBuilder.build()`
  (#801, read as a draft, without its handle on the latest object, which nothing reads once the outbox sends).
- `SupervisedObject`, private to the supervisor: one per builder, its latest object, closed at the shutdown.
- 30 brings the port, the builder, their contract and fakes, and the aMule client; 35 the webui and the notifier.
- The restart policy still decides until block 40. The glossary gains `restartable builder`.

### Block 40, the supervisor counts the bugs

- Each `SupervisedObject` keeps whether each of its object's latest turns met a bug, judged by `BUGS`' thresholds
  through `HealthRule.state_after`, forgotten at each rebuild, unknown until three turns, and its rebuilds in vain.
- The supervisor records each turn of the object's works there, never in `NodeHealth`; it rebuilds at once when they
  turn failing, three rebuilds in vain at most, then none until block 50, as on `main`.
- `RestartPolicy`, `RestartRequest`, `RestartRunner`, `node_restart_policy` and the restart policy's
  `HealthSubscriberBuiltLater` go; `BUGS` leaves every dependency's rules, and the four that held it alone go.
- A rebuild raising an `ExpectedError` counts in vain, logged in one warning line (the lot 4b spec's D15).
- The glossary's `bugs rule`, `restart policy`, `rebuild in vain`, `restartable` and `supervisor` lines are corrected.

### Block 45, the rebuild waits

- The rebuild waits 1, then 2, then 4 minutes, in memory.

### Block 50, the crawler's restart

- At the third rebuild in vain: its alert dispatched, `operations` audience, "client amuled rebuilt 3 times in vain:
  the crawler restarts", then the shutdown requested with an error; the lifecycle empties the outbox, closes every
  object and exits non-zero.
- `deploy/compose.yml` keeps `restart: unless-stopped`, which restarts the `p2pwatch` container whatever its exit
  code; `ed2k` is untouched.

### Block 55, each rule carrying its alert

- An external dependency's `rules`, a mapping from each rule to its `HealthAlert` or `None`, `HealthTransition`
  carrying the alert of its rule; `NodeHealth`, built with the dispatcher, dispatches it; the health alerter, its
  `_RULES_WITHOUT_AN_ALERT` and the alerts' `HealthSubscriberBuiltLater` go.
- Download tracking's dependency split: `DISK_SPACE_LOW` on the download disk, `CONNECTED_TO_NO_NETWORK` on amuled,
  recorded whether or not the node downloads.
- The glossary gains `health alert`; its `health alerter` line goes.

### Blocks 60 and 65, the refused password

- 60: a rule on amuled, "password refused", failing at one detection, healthy again at one reading without it; the
  status reading alone records it, detected on `ClientAuthError`, not detected on any answered reading, nothing when
  amuled is unreachable. Its alert, `operations` audience: "amuled refuses the password: check the configuration", its
  end "amuled accepts the password again". The glossary gains `password refused`.
- 65: the client tolerates a refused password at its login as it tolerates an amuled not listening yet; after a
  refused login, every call raises `ClientAuthError` at once, without reaching amuleapi, until the next login, 1 minute
  later, then twice as long each time, 30 minutes at most.

## Appendix B. Acceptance, in detail

| Row | Test | Fails unless |
|---|---|---|
| A bug at every turn of the client's works | a supervisor test on virtual time, every work over a fake client raising | rebuilds start 1, 2, then 4 min after each in vain, the alert is dispatched and the shutdown is requested with an error after the third |
| One keyword's search | a supervisor test, one of three works raising at each turn | no rebuild in 30 turns, each bug logged with its trace |
| Two in vain, ten healthy, then bugs | a supervisor test | the next rebuild comes 1 min after the bugs turn failing |
| The webui's thread dying | block 35's webui test, its thread stopped | a new thread serves |
| A bug at every send of the notifier | a supervisor test, a fake notifier raising | the notifier rebuilt after 1, 2, then 4 min, then the shutdown requested with an error |
| A bug in a Kad search | a supervisor test reading the log | no line names `channel amuled kad` with `bugs` |
| A refused password at the start | a composition test, a fake amuleapi refusing the password | the node runs, the alert is dispatched, two logins never closer than 60 s; at the release candidate, on the node |
| A refused password while running | a status watcher test | the alert at the first refused reading |
| The password right again | a status watcher test | the end at the first answered reading |
| Connected to no network | a status watcher test, downloads off | amuled's rule failing |
| One service refusing | a notifier work test | its "sends failed" rule failing, no alert dispatched |
| A notification decided, then stopped | an outbox test over the SQLite store: leave, stop, read back | the entry sent after the start; at the release candidate, on the node |
| A decision's write and its notification | the real callers (`file_judge`, `download_tracker`, `source_watcher`) and the real dispatcher over a spy outbox whose `leave` asserts that a `loop.call_soon` callback, scheduled before the decision's write, has not run yet | the flag still unset when `leave` runs |
| `local.db` refusing every write | an outbox test over a store raising `StoreError` | every entry sent, the local database's alert dispatched |
| The third rebuild in vain, `local.db` refusing | a lifecycle test | the alert reaches the fake notifier before the exit |
| Two services, one refusing | a notifier work test | the refusing service's send tried once, the other sent once |

## Appendix C. Facts

| Probe | Result |
|---|---|
| `docker run -d --restart on-failure:2 alpine:3.20 sh -c 'sleep 11; exit 1'`, inspected after 90 s, Docker 29.9.2, 2026-11-18 | `restarts=2 status=exited exit=1`: the count never resets, each run past Docker's 10 s |
| Docker's documentation, restart policies | "The `on-failure` policy only prompts a restart if the container exits with a failure. It doesn't restart the container if the daemon restarts." |
| `deploy/compose.yml` | `restart: unless-stopped` |
| aMule 3.2.0's `docs/api/REFERENCE.md`, "Rate limiting" | the login limiter locks an IP out for 300 s after 5 refused logins in 60 s; a successful login does not clear it |
| The client's `open()` | tolerates an amuled not listening yet; raises on a refused password |
| Block sizes, section 5 | estimated on `main` at `190cc145` from `git grep -w` counts of each name a block renames or removes and the lines of each module it rewrites, by an estimating agent; no `git diff` measured |

## Appendix D. For lot 7

What the operator pages must say, extending the lot 4b spec's appendix D:

- A refused password no longer stops the node, at its start included: an alert asks to check the configuration.
- A node whose rebuilds repair nothing restarts its crawler every 7 minutes and its start, an alert at each round.
- A notification may be sent twice after a restart; one refused by its service is not sent again.
- The local database's alert: the notifications still go out, but would be lost at the next restart.

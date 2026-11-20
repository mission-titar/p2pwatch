---
paths:
  - "packages/**"
  - "agents/specs/**"
---

# Glossary

The words the code, the docs and the specs share (`.claude/CLAUDE.md`, Naming).

| Word | Means | Never |
|---|---|---|
| `network` | `Network`, a file identity's namespace; eD2k covers Kad | for `ed2k`/`kad`: that is a channel |
| `channel` | one search channel of a client: `ed2k`, `kad` | `network` |
| `connected` | a channel has joined its network (an eD2k server, the Kad DHT) | `on_network` |
| `connectable` | peers can open a connection to it: one of our channels, or a source | `directly_reachable`, `high_id` |
| `client` | a port object driving a P2P client; `client_name` is its configured label | `instance`, a bare `name` |
| `node` | one running p2pwatch, `node_id` | `instance` |
| `file` | a `FileKey`: `network` and `native_id` | a string |
| `native_id` | the network's own file id (MD4 on eD2k) | `ed2k_hash` past the mapper |
| `filename` | a file's name, a string: `latest_filename`, `best_filename`, `known_filenames` | `name`, `file_name` |
| `source` | a peer sharing a file, `SourceKey`; `source_name` its advertised name | a bare `name` beside a filename |
| `source point` | `SourcePoint`, one source's reading of one of our downloads with its role, a carried one included, and its node, kept in catalog.db; `EarlierPoints` what this node's earlier points tell of a source | a sharing period, which spans consecutive ones |
| `contact point` | `ContactPoint`, the server a source connects through, as its network names one (`ip:port` on eD2k), built only valid: `parse_contact_point` gives `None` for any other text | a peer's address, which the catalog never stores |
| `latest point` | `LatestPoint`, a source's latest point under one of its variants: its role, its instant, its session's received bytes; `carried_role` carries its role to a reading in a passing state, `EarlierPoints.of` reduces a source's earlier ones | `last point` |
| `reported file` | `ReportedFile`, what the network reports of a file, with no instant: the mapper builds it, a `SearchAnswer` carries it | `observation` |
| `observation` | `FileObservation`, a reported file, its `observed_at`, the instant the crawler learned of it, stamped right before the write, and its node; every catalog read returns it whole, at the size its file was first recorded at | a reported file, `sighting` |
| `cataloguer` | `Cataloguer`, records a reported file as an observation, then has the file judge judge it again | `record_observation`, which is the Writer's |
| `file judge` | `FileJudge`, judges a file on every filename the catalog knows and records the decisions that changed, built once and shared by the cataloguer and the reevaluation | a decision helper |
| `candidate` | a `FileCandidate`, one name of a file and its metadata, the matcher's input; a `DownloadCandidate` is a file with a download-tier decision | `names` |
| `target` | an episode segment to recover: `target_id`, `TargetSegment`, its `letter` | `segment` for the letter; Kad's keyword target, which is a `kad_word` |
| `tier` | `DecisionTier`, a decision's strength: `catalog`, `notify`, `download`, its `rank` their order, `identifies_target` false for `catalog` alone | `before`, `after`; `retracted`, which is a retraction |
| `retraction` | `Retraction`, a file that no longer matches a target, appended since the catalog has no delete; a file's latest decision for a target, `FileTargetDecision`, is a `DecisionRecord` or a retraction | a fourth tier |
| `coverage` | `TargetCoverage`, how far a target is recovered: its `TargetCoverageStatus`, its best tier and its file count, the decisions whose tier identifies no target left out | `progress` |
| `test coverage` | `TestCoverage`, a module's statements and branches, those its package's test run ran and those its own tests ran: `TestCoverageReader` reads it from `.coverage` | a bare `coverage`, which is a target's |
| `file history` | `FileHistory`, a file as its page shows it: its observations over an interval, its latest one, its known filenames, its current decisions | `file detail` |
| `dated decision` | `DatedDecision`, a file's `FileTargetDecision` with its `decided_at` and its `node_id`, what `record_decisions` writes; apart since the anti-redundancy compares the decision alone | `decision view` |
| `interval` | `Interval`, the stretch of wall-clock time a page reads, at most 7 days, resolved from the ends a request asks for | `range`, `period` |
| `sharing period` | `SharingPeriod`, one source's consecutive readings on one file by one node: its first and last reading, the bytes received; a page reads them in a `PeriodWindow` | `source range` |
| `catalog entry` | `CatalogEntry`, a file as a listing shows it: its latest observation, its current decisions | `file row` |
| `known source` | `KnownSource`, a source with a user hash as the sources list shows it: its latest `source_name`, its latest reading, its file count | `source row` |
| `source naming` | `SourceNaming`, a source under one `source_name` it carried: its latest reading and its file count under that name | `source row` |
| `source history` | `SourceHistory`, a source as its page shows it: a page of its source namings, its sharing periods over every file, their files' best filenames | `source detail` |
| `source name history` | `SourceNameHistory`, a `source_name` as its page shows it: a page of the source namings that carried it, its sharing periods without a user hash, their files' best filenames | `name detail` |
| `search text` | `search_text`, the text a listed name must contain, or a listed source's hash prefix | `query`, which is SQL's |
| `token` | a named matcher of the policy (`tokens:`) | a word of a text |
| `word` | a piece of normalized text | `token` |
| `token expression` | `TokenExpression`, an `all`, `any` or `not` over tokens: a rule's body, a composite token or an inline operand | `condition` |
| `reevaluation` | re-judging every file when the policy changed | `backfill` |
| `tracked` | a download with a row in `downloads`, whatever its state: `TrackedDownload` | `downloaded`, `active` |
| `download status` | `DownloadStatus`, a download as its client lists it: its bytes, its `completed` signal, its `WaitingReason` or `FailureReason` | a tracked download, which is ours |
| `node state` | `NodeState`, what a node holds of its own: its identity, its tracked downloads, its search backoffs | `node info` |
| `query answer` | `QueryAnswer`, a console query's columns and first rows, each cell as text; `QueryFailure` when it gave none | `result` |
| `response model` | what a driving port returns, named from its use case's verb: `FileListing`, `NodeDescription` | `result`, `view` |
| `display` | a `<Thing>Display`, the view model a webui template renders, its values already text | `view` |
| `wake` | `Waker` wakes the loop waiting on a `WakeSubject` | `signal`, `nudge`, a string subject |
| `run state` | whether the crawler's shutdown was requested: `RunStateWriter` requests it, `RunStateReader` reads it and waits until it is | `control` |
| `fake` | a double that works, as its port promises: a store reads back what it was written, a clock moves | a stub or a spy, which keep the `Fake` prefix for now |
| `stub` | a double whose reads return what its test gave it, whatever was written: `FakeSourcePointStore` | a fake |
| `spy` | a double that keeps the calls it receives for its test to read: `FakeNotifier` | a fake |
| `contract` | a port's promise as a test suite: `<Port>Contract`, run by a `Test<Implementation>` subclass per implementation | an adapter's error mapping |
| `store` | one object implementing a `<Thing>Writer` and its `<Thing>Reader` over one state, the reader reading what the writer wrote: a fake's is `Fake<Thing>Store` | a fake for each port of the pair |
| `record`, `set` | a `Writer`'s two verbs: `record_` adds a fact and leaves the earlier ones (an observation, a decision, the node id written once), `set_` replaces a current value | `write_`, `save_`, `mark_`, `publish` |
| `status reading` | `StatusReading`, a client's status at one read, its `status` `None` when its API did not answer; a `PublishedReading` is one `InMemoryStatusReadingStore` holds, with its `published_at` on the monotonic clock | a source's reading |
| `first useful`, `reappeared` | a source's two alerts | `new`, `useful again` |
| `audience` | who a notification is for: `community`, `operations` | `tag`, `channel` |
| `notification` | `Notification`, what a `Notifier` sends each service of an audience, carrying its node: a `RelayedLogLine` relays an event's log line unchanged; a community one is a typed kind, a `TierRise`, a `SourceAlert` or a `CompletedDownload`, which the notifier writes out | a log line, which an operations notification only relays |
| `node metric` | a measurement of the node's own running (searches done, free disk, the crawler up), which Prometheus reads: a `NodeCounter` or a `NodeGauge` names one, with its description and its label class (`ChannelLabels`, `ClientLabels`, `DecisionLabels`, `SourceAlertLabels`, or none); `CounterIncrement` and `GaugeSetting` are what the policy writes, `NodeMetricSample` is one series and its current value | a bare `metric`; a file's or a source's figures |
| `health state` | `HealthState`, a part's state of health, as one rule sees it: unknown at first, then healthy or failing | `status`, a client's |
| `health rule` | `HealthRule`, a rule judging a part's health from its latest checks, such as "aMule does not answer": failing once detected 3 times in a row, healthy again once detected fewer than 2 times in the last 10 | a health `condition` |
| `detected` | what a rule saw or not at one check, the boolean `NodeHealth.record` takes; `Detections` counts them among the latest checks, such as "2 among the last 10" | `failure`, `success`, `outcome`, `problem` |
| `external dependency` | `ExternalDependency`, something the node depends on and does not control, which can have an outage, its health tracked: the aMule client, one of its channels, download tracking, a notification service, the local database; `part` is its plain word, in prose, the log and local names (`service_parts`) | `component`, `unit`, `service` |
| `outage` | something failing outside the program, such as aMule not answering or Kad off its network: a rule of an external dependency failing tells it | a bug, which is our code's |
| `health transition` | `HealthTransition`, a change of one part's state under one rule, such as the aMule client going from healthy to failing | `event`, the observability's |
| `node health` | `NodeHealth`, the node's health: every part's checks come here through `record(on=..., rule=..., detected=...)`, and each change is logged and passed on to the alerts | `recorder`, `registry` |
| `health alerter` | `HealthAlerter`, sends the client's, its channels', the download disk's and the local database's alerts when their health changes: "amuled unreachable for 2 min" when the client turns failing, "amuled reachable again" when it turns healthy | `translator` |
| `inaccessible path` | `InaccessiblePathError`, a path the filesystem refuses to examine (removed, under a file, behind a directory it cannot search, its name too long): the expected error of `FreeSpaceMeter` and `CatalogFinder` | a raw `OSError` past its adapter |
| `expected error` | `ExpectedError`, an error the code expects from outside, the base of every error a driven port declares: aMule down (`ClientError`), a store refusing a write (`StoreError`) | a `declared failure` |
| `bug` | an exception nobody expected: anything a turn raises but an `ExpectedError` | an `unexpected error`, a `failure` |
| `bugs rule` | `BUGS`, the thresholds the supervisor judges an object's bugs by, over every turn of its works: failing once 3 in a row met a bug, healthy again under 2 in the last 10; forgotten at each rebuild, never a rule of an external dependency, and no alert names it | a failures rule; a channel's bugs, which are the object's |
| `searches failed` | `SEARCHES_FAILED`, a channel's health rule: each search records whether the network refused it (`SearchFailedError`), failing once 3 in a row were refused, healthy again under 2 in the last 10; an unreachable client or a refused password records nothing, and no alert names it | a search's bug, which the supervisor counts on its object |
| `connected to no network` | `CONNECTED_TO_NO_NETWORK`, download tracking's health rule: each status reading records whether no channel of the client is connected, failing at 6 readings in a row, healthy again under 2 in the last 10; an unreachable reading records nothing, and no alert names it | a channel's `not connected` |
| `sends failed` | `SENDS_FAILED`, each notification service's health rule: once a send has ended, the notifier's work records on its service's part whether it failed, refused by the service or past `notification_timeout_seconds`, failing once 3 in a row failed, healthy again under 2 in the last 10; a bug of the notifier records nothing on it, and no alert names it, since it would be sent through that service | a send's bug, which the supervisor counts on the notifier |
| `saves failed` | `SAVES_FAILED`, the local database's health rule: at each turn, the notifier's work records on it whether the outbox's latest save failed (a `StoreError`), failing once 3 in a row failed, healthy again under 2 in the last 10; its alert "notifications not saved in local.db: lost at the next restart" goes out from memory, its end "notifications saved again" | a send's failure, which is `sends failed`'s |
| `notification service` | `NotificationService`, one service the notifier sends to, one per configured URL, named by its URL's scheme and its audience (`discord community`, a second alike `discord community 2`), never by its URL, which carries a webhook's token; its part is `notifier discord community` | an `ExternalDependency`, which is its part; a bare `service` outside the notifier's own API (`services()`, `notify(service, ...)`) |
| `notification outbox` | `NotificationOutbox`, the notifications left to send, in memory, one entry per notification and service, a `PendingNotification`: the dispatcher leaves one without awaiting anything, the notifier's work sends the oldest and removes it once its send has ended, a cancelled send keeping its entry; saved in `local.db` at each change, read back when built, an entry for a service no longer configured dropped | a queue, a buffer |
| `local database` | `local.db` as an external dependency, `local database` in the log: judged on the outbox's saves alone, by `saves failed` | the store, an adapter over it |
| `notifier's work` | `NotificationSender`, `notification sending` in the log: each turn sends the oldest notification left in the outbox within `notification_timeout_seconds`, and records its service's sends and the outbox's latest save; at the shutdown, the lifecycle has one send what is left | the dispatcher, which only leaves a notification |
| `notification refused` | `NotificationRefusedError`, the expected error a `Notifier` raises when a service refuses a send, such as a Discord webhook answering 404 | a timeout, which the notifier's work reads alone |
| `config problem` | `ConfigProblem`, one problem of a config file: the file, the key or none, the message | a refusal, an error |
| `schema` | a pydantic model of a config file as written, in the config adapter only: `CrawlerConfigSchema` | the domain object it builds |
| `error_label` | the label a parser prints in its errors | `what`, `label`, `field` |
| `wall clock` | `WallClock`, the UTC time of day: every stamp a row, an event or a display carries | an interval or a deadline kept in memory |
| `monotonic clock` | `MonotonicClock`, its `MonotonicInstant`s: every interval and deadline kept in memory; `p2pwatch_amule`'s only sleeps | a stamp, anything persisted |
| `ticker` | `Ticker`, calls back every period while a long synchronous operation holds its thread, for a progress line; `ThreadingTicker` waits on a thread of its own, since the operation holds the event loop | a `MonotonicClock` sleep, which runs on that loop |
| `backoff saver` | `BackoffSaver`, sets the backoff every search shares in its store after each search that changed it, so a node restarted while Kad refuses its searches waits out what is left of Kad's backoff | `BackoffRegistry`, which holds the backoff in memory |
| `latest search start` | `LatestSearchStart`, when a client last started a search in one scope of a channel, kept in `local.db` so that a client built anew waits out the spacing: the scope `''` for all of eD2k, a Kad word on Kad | `last search start`; a bare `scope`, without its channel |
| `persisted wait` | a wait that survives a restart: its start on the wall clock and its duration, clamped by `remaining_wait` when the node meets it again | a deadline persisted alone |
| `own tests` | a module's own tests: the test files named after it, in the directory mirroring its own (`tests/a/test_b*.py` for `src/<pkg>/a/b.py`) | a test that runs the module in passing |
| `claim` | one of our OpenVEX `not_affected` statements: an advisory id and its justification; `read_claims` returns a VEX file's justifications by advisory id; a `ClaimProblem` is what a check finds wrong with an advisory's claims, its message worded once | `statement` past `OpenVexReader`; `violation` for a `ClaimProblem`, which may contradict no premise |
| `premise` | the falsifiable fact a claim rests on: an image premise holds of an image's SBOM, its descriptor in `PREMISES`; a source premise holds of our code, a source rule checks it | the claim itself |
| `source rule` | the ast-grep rule that checks one source premise, in `packages/vex_checks/ast-grep/rules/`, its id the advisory id of the claim it backs; `poe vex-source-claims` scans them | a rule of `ast-grep/rules/`, which checks a code pattern |
| `ring` | one of a hexagon's four concentric parts, read from the path: `domain`, `application`, `adapters`, `composition`; `application`'s `ports`, `use_cases`, `steps` and lifecycle are tach's layers inside it | `layer`, tach's word |
| `hexagon` | one application, its core and its adapters, which never imports another hexagon; `p2pwatch` is one | a package |
| `driving` | the side that calls the core: a driving port is what a use case offers, a driving adapter calls it (the command line, the webui) | `primary`, `inbound` |
| `driven` | the side the core calls: a driven port is what the core needs, a driven adapter implements it (SQLite, amuleapi) | `secondary`, `outbound` |
| `use case` | an operation called from outside through a driving port, in `application/use_cases/`: `ValidateConfig` | `service`, `interactor` |
| `step` | a piece of the program the composition builds, behind no driving port: a class in `application/steps/`, one per module, `NodeIdResolver` | a use case |
| `work`, `turn` | `Work`, a task the node repeats: a wait, then a turn, again, such as `StatusWatcher` reading aMule's status every minute; each work computes its wait from its own state, and the first turn waits too | a `loop`; an asyncio `Task` |
| `supervisor` | `Supervisor`, takes the turns of the works of each object it built, each after its wait, until the shutdown is requested, then cancels them all; a turn that raises or outlasts its time limit fails alone, a bug's work waiting at least 60 s before its next turn; it has each restartable builder build its first object (`build_first`) and keeps the latest each built in a `SupervisedObject`, which counts whether each turn of its works met a bug: once they turn failing, the supervisor rebuilds it in a task of its own, stopping its works, then, after 1 min doubled at each rebuild in vain, closing it and having its builder build another; the latest of each is closed at the shutdown | `LoopSupervisor` |
| `restartable` | `Restartable`, an object holding state in memory that the node can rebuild, such as a client logged in to aMule: built whole, it never changes, hands back the works over its state (`works()`) and releases it (`close()`), rebuilt by the supervisor when the bugs of its works keep coming back; `NotifierRestartable` holds the notifier and the notifier's work over it | a state `owner`; a holder that swaps its state |
| `restartable builder` | `RestartableBuilder`, builds a new restartable at each call, the first included, such as `AmuleClientRestartableBuilder` logging a client in; its name is the objects' in the log, `client amuled` | a factory |
| `rebuild in vain` | a rebuild after which the object's bugs turn failing again before they are healthy, or one that raised: after three, the object is not restarted again, the count reset once its bugs are healthy | a `useless` restart |
| `time limit` | the longest a work's turn may last, the sum of the bounds on its turn's path plus 5 minutes, which `AmuleWorkTimeLimits` derives for the works over the client, the webui's watch taking the margin alone, the notifier's work one send's timeout and the margin; a `SupervisedWork` is a work and its limit, and a turn still running then is cut, a `TurnTimeoutError`, a bug | a `timeout`, a request's; a `deadline`, the shutdown's |
| `webui thread watch` | `WebuiThreadWatch`, a work that looks every minute whether the webui's thread still runs, `webui` in the log: a thread that has ended is a bug of the webui, whose bugs turning failing have the supervisor serve it on a thread `WebuiRestartableBuilder` builds anew | `liveness`; a health check, which an HTTP endpoint answers |
| `lifecycle` | the program from its start to its stop, which the composition runs: `CrawlerLifecycle`, `PortSyncLifecycle`, behind no driving port | `app` |
| `micros` | an integer of microseconds: an instant counts from the epoch; a column holding one is named `<x>_micros` too | a bare `_at` on an `int`, a column's included |
| `id`, `db`, `sql`, `url`, `api`, `json`, `ecid`, `mib`, `iso`, `min`, `max`, `conf`, `argv`, `env`, `cwd`, `uid`, `gid` | the abbreviations allowed (`conf`: aMule's `amule.conf`; `argv`, `env`, `cwd`: what a `__main__.py` reads of its process; `uid`, `gid`: POSIX's user and group ids) | `dir` for `directory` |

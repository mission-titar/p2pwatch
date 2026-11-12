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
| `token expression` | `TokenExpression`, an `all`, `any` or `not` over tokens: a rule's body, a composite token or an inline operand | `condition`, a health word |
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
| `audience` | who a notification is for: `community`, `operations` | `tag` (apprise's keyword aside), `channel` |
| `notification` | `Notification`, what a `Notifier` sends an audience, carrying its node: a `RelayedLogLine` relays an event's log line unchanged; a community one is a typed kind, a `TierRise`, a `SourceAlert` or a `CompletedDownload`, which the notifier writes out; each one's outcome recorded on the notifier's component | a log line, which an operations notification only relays |
| `node metric` | a measurement of the node's own running (searches done, free disk, the crawler up), which Prometheus reads: a `NodeCounter` or a `NodeGauge` names one, with its description and its label class (`ChannelLabels`, `ClientLabels`, `DecisionLabels`, `SourceAlertLabels`, or none); `CounterIncrement` and `GaugeSetting` are what the policy writes, `NodeMetricSample` is one series and its current value | a bare `metric`; a file's or a source's figures |
| `declared failure` | `DeclaredFailure`, a failure a contract names, an outcome's reason: the base of every failure a driven port raises (`NotificationRefused` the notifier's), or carried by an outcome that raises nothing (`ClientNotAnswering`, `ChannelNotConnected`, `ChannelNotConnectable`, `NoChannelConnected`, `FreeSpaceBelowFloor` with its figures, `NotificationTimedOut` a send past the notification timeout) | an `expected error` |
| `outcome` | `Outcome`, what one reading or one unit of work gave: a success, or its reason | `result` |
| `bug` | `Bug`, an outcome's reason outside every contract: a turn or a notification raising anything but a declared failure | an `unexpected error` |
| `floor after a bug` | `FLOOR_AFTER_A_BUG`, the least wait before a turn that follows a bug, the later of it and the work's own wait | a backoff, which is the network's |
| `time limit` | the longest a work's turn may take, a `SupervisedWork` carrying both: the sum of the bounds on its turn's path plus a fixed allowance, `AmuleTurnTimeLimits` deriving it; a turn past it is cut, a `TurnPastItsLimit` recorded as a `Bug` | a `timeout`, a request's; a `deadline`, the shutdown's |
| `outcome source` | `OutcomeSource`, what records an outcome (`STATUS_API_ANSWER`, `TURNS` a unit of work's, the supervisor's of a turn or the dispatcher's of a notification, `SEARCHES` a search turn's success or declared failure, a bug recording nothing, `FREE_SPACE_READING` the download disk's): a condition reads one source, whose successes count for it alone | `origin` |
| `health` | `Health`, a condition's state: `unknown` until its window holds its smallest entry's outcomes, `healthy`, `degraded`, `failing` | `status`, a client's |
| `health condition` | `HealthCondition`, the failures of one reason among a component's last outcomes of one source, entering a `Band`, `failing` or `degraded`, both by default, at `AtLeast` and leaving under a stricter `Below`, a milder band entering by its own entry alone; its `ConditionWindow` the component's state | a bare `condition`, a token expression |
| `bugs condition` | `BUGS`, the health condition counting the `Bug` outcomes of `TURNS` under the default bands, carried by every component a work feeds and by the notifier's | a condition over every failure |
| `component` | `Component`, a part of the node judged by its conditions, its `ComponentLabels` naming it to the events and metrics | `unit`, `service` |
| `health transition` | `HealthTransition`, one condition of one component changing its health, with the outcome that changed it | `event`, the observability's |
| `health recorder` | `HealthRecorder`, every outcome's one path: recorded on its component, each transition logged in one line and handed to its subscribers in order | `registry` |
| `health event translator` | `HealthEventTranslator`, the recorder's subscriber turning the readings' transitions into today's connectivity and disk events | an `alert`, lot 4c's |
| `inaccessible path` | `InaccessiblePathError`, a path the filesystem refuses to examine (removed, under a file, behind a directory it cannot search, its name too long): the declared failure of `FreeSpaceMeter` and `CatalogFinder` | a raw `OSError` past its adapter |
| `config problem` | `ConfigProblem`, one problem of a config file: the file, the key or none, the message | a refusal, an error |
| `schema` | a pydantic model of a config file as written, in the config adapter only: `CrawlerConfigSchema` | the domain object it builds |
| `error_label` | the label a parser prints in its errors | `what`, `label`, `field` |
| `wall clock` | `WallClock`, the UTC time of day: every stamp a row, an event or a display carries | an interval or a deadline kept in memory |
| `monotonic clock` | `MonotonicClock`, its `MonotonicInstant`s: every interval and deadline kept in memory; `p2pwatch_amule`'s only sleeps | a stamp, anything persisted |
| `ticker` | `Ticker`, calls back every period while a long synchronous operation holds its thread, for a progress line; `ThreadingTicker` waits on a thread of its own, since the operation holds the event loop | a `MonotonicClock` sleep, which runs on that loop |
| `backoff saver` | `BackoffSaver`, the search works' shared save of the backoff: its snapshot taken at the first turn, once the lifecycle resumed the waits, then a save after each turn that changed it | `BackoffRegistry`, which holds the waits |
| `latest search start` | `LatestSearchStart`, a client's latest search start in one scope of a channel, the start of a persisted wait of the adapter's spacing: the scope `''` for a channel-wide spacing (eD2k's), a Kad word on Kad | `last search start`; a bare `scope`, without its channel |
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
| `step` | a stage of the program the composition builds, behind no driving port: a class in `application/steps/`, one per module, `NodeIdResolver` | a use case |
| `work`, `turn` | `Work`, what the supervisor runs again and again, an ABC a step subclasses (`StatusSensor`): a turn is one call to `run_once()`, after `wait_for_next_turn()`, the first turn included, the wait computed from the work's own state | a `loop`; a `task`, asyncio's |
| `supervisor` | `Supervisor`, runs each work's turns until the shutdown is requested, then cancels them, a restart in flight included; a turn that raises or passes its time limit fails alone, its outcome logged and recorded by `TURNS` on the components its `SupervisedWork` feeds; each restart the restart policy requests runs in a task of its own, the works feeding the owner's components stopped first | `LoopSupervisor` |
| `webui liveness` | `WebuiLiveness`, the work looking at the webui's thread each status period, a thread that has ended a `WebuiFallen`, recorded as a `Bug` on the webui's component: the webui serves until it falls, and no cancellation reaches a thread | a health check, lot 4c's endpoints |
| `state owner` | `StateOwner`, what holds an in-memory state a restart repairs (the aMule client's session, its eD2k lock, its Kad slots, its caches; the webui's thread; the notifier's apprise groups): `restart()` builds it anew and adds the works relying on it, if any, to the supervisor again; the composition names each component's owner, if any, `AmuleClientOwner` the client's, `WebuiThreadOwner` the webui's, `NotifierOwner` the notifier's, through which the dispatcher reaches the notifier at each send | a factory, which never leaves the composition |
| `restart policy` | `RestartPolicy`, the recorder's subscriber restarting the owner of a component whose bugs condition enters failing, its bugs windows emptied, at most three useless restarts (a bugs condition of its components failing again before all are healthy, or a rebuild that raised), the count reset once all are healthy again; a component without an owner only logged | a backoff, the network's |
| `lifecycle` | the program from its start to its stop, which the composition runs: `CrawlerLifecycle`, `PortSyncLifecycle`, behind no driving port | `app` |
| `micros` | an integer of microseconds: an instant counts from the epoch; a column holding one is named `<x>_micros` too | a bare `_at` on an `int`, a column's included |
| `id`, `db`, `sql`, `url`, `api`, `json`, `ecid`, `mib`, `iso`, `min`, `max`, `conf`, `argv`, `env`, `cwd`, `uid`, `gid` | the abbreviations allowed (`conf`: aMule's `amule.conf`; `argv`, `env`, `cwd`: what a `__main__.py` reads of its process; `uid`, `gid`: POSIX's user and group ids) | `dir` for `directory` |

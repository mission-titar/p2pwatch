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
| `dated decision` | `DatedDecision`, a file's `FileTargetDecision` with its `decided_at` and its `node_id`, what `record_decision` writes; apart since the anti-redundancy compares the decision alone | `decision view` |
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
| `reevaluation` | re-judging every file when the policy changed | `backfill` |
| `tracked` | a download with a row in `downloads`, whatever its state: `TrackedDownload` | `downloaded`, `active` |
| `download status` | `DownloadStatus`, a download as its client lists it: its bytes, its `completed` signal, its `WaitingReason` or `FailureReason` | a tracked download, which is ours |
| `node state` | `NodeState`, what a node holds of its own: its identity, its tracked downloads, its search backoffs | `node info` |
| `query answer` | `QueryAnswer`, a console query's columns and first rows, each cell as text; `QueryFailure` when it gave none | `result` |
| `response model` | what a driving port returns, named from its use case's verb: `FileListing`, `NodeDescription` | `result`, `view` |
| `display` | a `<Thing>Display`, the view model a webui template renders, its values already text | `view` |
| `wake` | `Waker` wakes the loop waiting on a `WakeSubject` | `signal`, `nudge`, a string subject |
| `run state` | whether the crawler searches or idles, and whether its shutdown was requested: `RunStateWriter` sets it, `RunStateReader` reads it and waits until it changes | `control` |
| `fake` | a double that works, as its port promises: a store reads back what it was written, a clock moves | a stub or a spy, which keep the `Fake` prefix for now |
| `stub` | a double whose reads return what its test gave it, whatever was written: `FakeSourcePointStore` | a fake |
| `spy` | a double that keeps the calls it receives for its test to read: `FakeNotifier` | a fake |
| `contract` | a port's promise as a test suite: `<Port>Contract`, run by a `Test<Implementation>` subclass per implementation | an adapter's error mapping |
| `store` | one object implementing a `<Thing>Writer` and its `<Thing>Reader` over one state, the reader reading what the writer wrote: a fake's is `Fake<Thing>Store` | a fake for each port of the pair |
| `record`, `set` | a `Writer`'s two verbs: `record_` adds a fact and leaves the earlier ones (an observation, a decision, the node id written once), `set_` replaces a current value | `write_`, `save_`, `mark_`, `publish` |
| `status reading` | `StatusReading`, a client's status at one read, its `status` `None` when its API did not answer; a `PublishedReading` is one `InMemoryStatusReadingStore` holds, with its `published_at` on the monotonic clock | a source's reading |
| `first useful`, `reappeared` | a source's two alerts | `new`, `useful again` |
| `audience` | who a notification is for: `community`, `operations` | `tag` (apprise's keyword aside), `channel` |
| `notification` | `Notification`, what a `Notifier` sends an audience, carrying its node: a `RelayedLogLine` relays an event's log line unchanged; a community one is a typed kind, a `TierRise`, a `SourceAlert` or a `CompletedDownload`, which the notifier writes out | a log line, which an operations notification only relays |
| `node metric` | a measurement of the node's own running (searches done, free disk, the crawler up), which Prometheus reads: a `NodeCounter` or a `NodeGauge` names one, with its description and its label class (`ChannelLabels`, `ClientLabels`, `DecisionLabels`, `SourceAlertLabels`, or none); `CounterIncrement` and `GaugeSetting` are what the policy writes, `NodeMetricSample` is one series and its current value | a bare `metric`; a file's or a source's figures |
| `config problem` | `ConfigProblem`, one problem of a config file: the file, the key or none, the message | a refusal, an error |
| `error_label` | the label a parser prints in its errors | `what`, `label`, `field` |
| `wall clock` | `WallClock`, the UTC time of day: every stamp a row, an event or a display carries | an interval or a deadline kept in memory |
| `monotonic clock` | `MonotonicClock`, its `MonotonicInstant`s: every interval and deadline kept in memory; `p2pwatch_amule`'s only sleeps | a stamp, anything persisted |
| `ticker` | `Ticker`, calls back every period while a long synchronous operation holds its thread, for a progress line; `ThreadingTicker` waits on a thread of its own, since the operation holds the event loop | a `MonotonicClock` sleep, which runs on that loop |
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
| `step` | a stage of the lifecycle's graph, called only by the lifecycle or another step: a class in `application/steps/`, one per module, `NodeIdResolver` | a use case |
| `lifecycle` | the program from its start to its stop, which the composition runs: `CrawlerLifecycle`, `PortSyncLifecycle`, behind no driving port | `app` |
| `micros` | an integer of microseconds: an instant counts from the epoch; a column holding one is named `<x>_micros` too | a bare `_at` on an `int`, a column's included |
| `id`, `db`, `sql`, `url`, `api`, `json`, `ecid`, `mib`, `iso`, `min`, `max`, `conf`, `argv`, `env`, `cwd`, `uid`, `gid` | the abbreviations allowed (`conf`: aMule's `amule.conf`; `argv`, `env`, `cwd`: what a `__main__.py` reads of its process; `uid`, `gid`: POSIX's user and group ids) | `dir` for `directory` |

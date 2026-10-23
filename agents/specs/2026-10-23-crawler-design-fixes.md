# Post-hexagonal corrections, lot C: the crawler's design fixes

- Date: 2026-10-23. Status: draft, awaiting review.
- Tier: Spec. Origin: the post-hexagonal ledger's rows A1 to A15, A17, R6, R7 and R11, the handoff's D8, the Discuss of 2026-10-23.
- Size: 34 blocks with the closing one, under this lot's ceiling of 36; blocks 10 and 30 mechanical, exempt.
- Paths are under `packages/crawler/src/p2pwatch/` unless noted; measured on `main` at `114f335e` (appendix D).

## In short

- The adapter reads `crawler.yml` and resolves `${NAME}`; the domain checks and builds the config, as the matching does.
- `validate-config` becomes a check: a report for a wrong config, an error for a broken file.
- Strings become types: the tiers, the retraction, the coverage status, the wake subject, the contact point.
- Rules leave the adapters: source point roles, merge's same-catalog rule, event dispatch, notification Markdown.
- The run state is read through its port: no `asyncio.Event` is left in the core.
- A domain object carries the node that produced it, and a Writer takes the object only.
- No dependency bags: each loop and each download stage is a class that receives what it uses and owns its state.
- Smaller fixes: client errors per operation, fixed values in the composition, its own resource stack, the backoff loaded at start.

## What an operator sees change

Exact messages, exit codes and logger names: appendix B.

- `${NAME}` is resolved in every string value of `crawler.yml`, not only six keys; an unset one anywhere refuses the start (D1).
- `merge` refuses an `--output` that is also one of its sources, before writing anything (D4).
- `validate-config` tells a broken file from a wrong one, and names the file (D3).
- The event lines, the download loop's lines and merge's skip line log under new logger names (D23, D28, D29).
- `/files` ignores an unknown tier filter instead of listing nothing (D14).
- Unchanged, and checked: DEBUG lines, notifications, metrics, webui pages, database schemas (Acceptance 4, 5, 17).

## Conventions

Each goes into `AGENTS.md` in the block where the whole tree first follows it (details: appendix A).

- **C1.** A Reader's method says what it gives back (`read_`, `iter_`, `is_` or `has_`, `wait_until_`). Naming, block 160.
- **C2.** The two lot-C exceptions end (`supervise_loops`, `RunStateReader`). Hard rules and Naming, block 160.
- **C3.** A parameter object only for values that form a concept, never a bag of dependencies. Hard rules, block 310.
- **C4.** The domain writes plain text; the Markdown is the adapter's. Hard rules, block 220.
- **C5.** A domain object carries who produced it; a Writer takes the object only. Naming, block 252.
- **C6.** "A broken input raises" reaches the crawler's `validate-config`. Hard rules, block 40.

## Decisions

Signatures, fields, interim states and counts for each decision: appendix A, under the same number.

### Config (A13, R6)

- **D1. The adapter resolves `${NAME}` in every string value of `crawler.yml` before the domain sees it.** Why: the
  operator's choice, so the domain never sees the environment and the adapter does not know the schema. Block 20.
- **D2. The domain checks the config and builds it, raising `InvalidConfigError` itself; `ConfigError` goes.** Why:
  as the matching parses its files in its domain, with one error type for one refusal. Block 30.
- **D3. `validate-config` returns a report of the problem it finds, and raises only on a broken file.** Why: the
  Hard rule "a broken input raises; a problem is a finding on a valid input". Block 40.

### Merge, errors, fixed values, composition (A6, A9, A10, A11, A12, A15, R11)

- **D4. `MergeCatalogs` alone holds the same-catalog rule, and refuses an output that is also a source.** Why: one
  rule in one place; a forced self-merge was never meant. Block 40.
- **D5. Each amuleapi method raises its own operation's port error; a refused read raises `ReadRejectedError`.** Why:
  a search refusal was catchable as a download refusal. Block 50.
- **D6. `MatchingExplainer` receives the engine the composition builds.** Why: one engine, safe to share since it
  keeps no state. Block 50.
- **D7. `PAGE_SIZE` moves to `application/use_cases/paging.py`.** Why: only the listing use cases read it. Block 60.
- **D8. The adapters' fixed values become composition constants, and the composition passes `max_filename_length`.**
  Why: a fixed value no option sets is the composition's, which passes real values, never a default. Block 60.
- **D9. The composition keeps its own resource stack; `PosixProcess` only handles the signals.** Why: a driving
  adapter owned the composition's resources. Block 70.
- **D10. `CrawlerLifecycle` resumes the persisted backoff waits at its start.** Why: a startup step belongs to the
  lifecycle, not to the composition. Block 70.

### Types where strings were (A5, A7, A8, A14)

- **D11. `WakeSubject` is the only type `Waker` takes.** Why: two loops shared a string one of them defined. Block 80.
- **D12. `DecisionTier`, in the matching domain, carries the tiers' order and the catalog rule.** Why: those rules
  were scattered over bare strings. Blocks 90 and 100.
- **D13. A retraction is a type of its own, beside `DecisionRecord`.** Why: the engine never produces it, so it is no
  fourth tier. Block 100.
- **D14. Every tier rule reads the type, the SQL included, and `/files` ignores an unknown tier.** Why: one
  definition of the order and of "catalog identifies no target". Block 110.
- **D15. `CoverageReader` returns `DecisionTier`s.** Why: a read port returns domain types. Block 120.
- **D16. The fresh-versus-persisted diff and the retraction rule move to the domain.** Why: a pure rule belongs to
  the domain. Block 120.

### Source points (A2, R7)

- **D17. A contact point is a domain type, built only valid.** Why: the store guarded what a type can guarantee.
  Block 130.
- **D18. The domain decides the source roles and reduces the earlier points; the store only reads and writes.** Why:
  a store decides nothing. Blocks 140, 150 and 155.
- **D19. `record_queued` returns nothing.** Why: a Writer returns nothing. Block 80.

### Run state (A1)

- **D20. `RunStateReader` gives the pause and the shutdown as predicates and waits; `reader-verbs` holds the Readers'
  verbs.** Why: the loops read the run state through its port, and a gate tool comes before a convention. Block 160.

### Observability (A3, A4)

- **D21. The dispatch is a step, `ObservabilityDispatcher.dispatch(event)`, which the steps call directly.** Why:
  orchestrating the core's events is the core's job, not a driven adapter's. Blocks 180 to 200.
- **D22. `Logger` gains `debug`.** Why: the four DEBUG events keep their level. Block 170.
- **D23. `Report` becomes `ObservabilityPlan`, and `describe` becomes `plan_observability`.** Why: "report" names a
  check's result elsewhere. Blocks 170 and 180.
- **D24. The domain produces typed community notifications; the apprise adapter writes their Markdown.** Why: the
  formatting is the adapter's. Block 220.
- **D25. An operations notification relays its log line unchanged.** Why: it has no text of its own, as today.
  Block 210.

### The node on the object (A17)

- **D26. Observations, decisions, source points, notifications and the events that notify carry their node.** Why: a
  domain object carries who produced it, so a Writer takes the object only. Blocks 155 and 230 to 252.

### Dependency bags (the handoff's D8)

- **D27. The `*Deps` bags go: each loop and each download stage is a class, its dependencies injected, its state
  its own.** Why: a bag of dependencies is a smell, and `DownloadDeps` also held the loop's state. Blocks 260 to 310.
- **D28. Block 10 moves the download cycle verbatim into its future classes' modules, the tests with it.** Why: the
  later blocks then edit small modules that already have their final names. Block 10.
- **D29. Until block 310, each new class rides `DownloadDeps`.** Why: each block stays green and readable alone.
  Blocks 280 to 300.

### Docs

- **D30. Each block updates the glossary and the docs that name what it changes.** Why: a name must not drift, and
  `docs/migration-4x.md` lists the operator-visible changes, which are v5's. Every block.

### Adapter loggers (the handoff's item)

- **D31. `GluetunForwardedPortClient` logs through `logging.getLogger(__name__)`, its `Logger` parameter gone.** Why:
  the logger rule then holds in every adapter, with no departure left. Block 70.

## Blocks

Strict TDD in every block, as `AGENTS.md` states it. Full contents, estimate sources and notes: appendices A and D.

| # | Branch | Holds | Lines, files |
|---|---|---|---|
| 10 | `refactor/download-cycle-split` | **mechanical, exempt**: this spec; the cycle split (D28) | 4942, 26 (measured) |
| 20 | `refactor/config-interpolation-walk` | the `${NAME}` walk (D1) | 260, 8 |
| 30 | `refactor/config-to-domain` | **mechanical, exempt**: the config to the domain (D2) | 150 to 2900, 14 |
| 40 | `refactor/validate-config-report` | `validate-config`'s report; merge's same-catalog rule (D3, D4) | 330, 16 |
| 50 | `refactor/client-read-errors` | client errors per operation; the explainer's engine (D5, D6) | 270, 15 |
| 60 | `refactor/fixed-values-to-composition` | `PAGE_SIZE`; fixed values to the composition (D7, D8) | 90, 18 |
| 70 | `refactor/composition-resource-stack` | the resource stack; backoff at start; gluetun's logger (D9, D10, D31) | 230, 13 |
| 80 | `refactor/wake-subject` | `WakeSubject`; `record_queued` returns nothing (D11, D19) | 150, 16 |
| 90 | `refactor/decision-tier` | `DecisionTier` in `catalog_matching` (D12) | 150, 10 |
| 100 | `refactor/retraction-type` | the crawler's tiers typed, `Retraction` (D12, D13) | 330, 19 |
| 110 | `refactor/tier-rules-from-type` | tier rules and SQL from the type (D14) | 230, 13 |
| 120 | `refactor/coverage-tiers-and-records-to-write` | coverage tiers; `records_to_write` (D15, D16) | 200, 11 |
| 130 | `refactor/contact-point` | `ContactPoint` (D17) | 200, 12 |
| 140 | `refactor/earlier-points-in-domain` | earlier points reduced in the domain (D18) | 200, 9 |
| 150 | `refactor/source-roles-in-domain` | source roles decided in the domain (D18) | 400, 14 |
| 155 | `refactor/source-point-node` | the source point carries its node (D18, D26) | 110, 9 |
| 160 | `refactor/run-state-waits` | run state predicates and waits; `reader-verbs` (D20) | 210, 17 |
| 170 | `refactor/observability-plan` | `ObservabilityPlan`, `Logger.debug` (D22, D23) | 170, 9 |
| 180 | `refactor/dispatch-step` | the dispatch step (D21) | 330, 12 |
| 190 | `refactor/dispatch-from-lifecycle-and-decisions` | the lifecycle and decision steps call `dispatch` (D21) | 420, 14 |
| 200 | `refactor/dispatch-from-loops` | the loops call `dispatch`; `EventEmitter` goes (D21) | 480, 13 |
| 210 | `refactor/relayed-log-line` | the notifier's new signature, `RelayedLogLine` (D25) | 330, 9 |
| 220 | `refactor/typed-notifications` | typed community notifications, Markdown in apprise (D24) | 410, 10 |
| 230 | `refactor/observation-node` | observations carry their node (D26) | 250, 19 |
| 240 | `refactor/dated-decision-writes` | decisions written as a `DatedDecision` (D26) | 280, 16 |
| 250 | `refactor/community-events-carry-node` | community events carry their node (D26) | 230, 13 |
| 252 | `refactor/operations-events-and-dispatch` | operations events carry their node; `dispatch(event)` (D26) | 240, 17 |
| 260 | `refactor/search-worker-dependencies` | `SearchWorker` without `WorkerDeps` (D27) | 420, 8 |
| 270 | `refactor/status-loop-class` | `StatusLoop` (D27) | 260, 6 |
| 280 | `refactor/download-tracker` | `DownloadTracker` (D27, D29) | 400, 8 |
| 290 | `refactor/download-decider-and-starter` | `DownloadDecider`, `DownloadStarter` (D27, D29) | 300, 8 |
| 300 | `refactor/source-watcher` | `SourceWatcher` (D27, D29) | 200, 6 |
| 310 | `refactor/download-cycle-class` | `DownloadCycle`, `DownloadLoop`; the bags gone (D27) | 400, 10 |
| 320 | `docs/crawler-design-fixes-wrap` | closing block: holistic findings, backlog, handoff | |

- Order: the move first; the config before R6 and A2; the tier types before A5, A7 and A17; A2 to A4 before A17; A1 and A3 before the classes.
- Soft spots: blocks 100 and 230 at 19 files, 252 at 17 to 19, 150, 200 and 220 near 500 lines, 280 to 300 not re-measured.

## Acceptance

Exact commands and what each prints on `main`: appendix C, same numbers.

1. No `asyncio.Event` in the core, no lot-C exception in `AGENTS.md`, and `reader-verbs` refuses a stray Reader verb.
2. The source point store carries no role, reduces nothing and drops no reading.
3. The dispatcher adapter and `EventEmitter` are gone, and the severity match is exhaustive.
4. Every event's log line, metrics and notifications are identical to `main`'s, byte for byte.
5. The webui's `/`, `/files` and a file page render identically to `main`'s.
6. The composition no longer loads the backoff.
7. No tier string or tier table is left, and `/files?tier=bogus` lists every file.
8. `ApiRejectedError` inherits no port error, each client operation raises its own, and the integration suites pass.
9. `merge` with its output among its sources is refused and writes nothing.
10. `PAGE_SIZE`, the resource stack, the second engine and the adapters' fixed values have moved.
11. An unset `${NAME}` under any key fails `validate-config`, naming the key.
12. No wake subject string is left.
13. No Writer and no notifier method takes `node_id`.
14. `validate-config` on a missing file prints one error line and exits 1, and the use case returns a report.
15. No Writer returns a value.
16. No `deps` or `*Deps` is left, and `run_download_cycle.py` is gone.
17. Nothing out of scope changes: deploy, security, migrations, Dockerfiles, workflows.
18. No adapter of any package receives the `Logger` port.
19. The gate is green at every block.

## Backlog

- **A copy before a migration that rewrites rows**: stays open; this lot adds no migration, but its release waits for it.
- **Contract tests for the fakes**: stays open and follows this lot, which settles the ports' final shape (run state, notifier, Writers).
- **The ast-grep rule tests bound to their rules by design**: stays open; this lot edits `core-import-names.yml` and adds `reader-verbs` the existing way.
- **The node page shows a node id set in `crawler.yml`**: stays open; A17 moves `node_id` onto the objects, `resolve_node_id` still records no configured id.
- **Multi network, stage 5**: stays open; it will implement the ports this lot reshapes (`ReadRejectedError`, the typed notification).
- Untouched, staying open: **Sort the files view by first seen**, **The webui in the visitor's time zone**, **The Grype scan back on p2pwatch at the v5 release**, **The VEX's Python claims applied by Grype**, **The metrics served by the webui on 8080**, **Every stamp an integer of microseconds**, **Adopt ty**, **Test quality**, **Mutation testing in the gate**.
## Appendix A: decision details

The lot applies the ledger `agents/reference/2026-10-22-post-hexagonal-audit.md`'s decisions without restating them;
the Discuss of 2026-10-23 settled what the ledger left open; the handoff is `agents/handoffs/2026-10-23 - handoff -
names and other hexagons.md`, "For lot C and after". The ledger rows, in full: A1 to A15, A17, R6 (with R6b and R6c in
the crawler), R7 and R11, in the crawler. The operator raised this lot's ceiling to 36 blocks and approved the
exemptions of blocks 10 and 30 on their rows.

### Conventions, in full

- **C1. A Reader's method says what it gives back**: `read_` a value, `iter_` an iterator, `is_` or `has_` a
  predicate, `wait_until_` a state reached. Naming, block 160 (the run state's waits are the first `wait_until_`).
  An ast-grep rule `reader-verbs`, twin of `writer-verbs`, refuses any other (D20).
- **C2. The two lot-C exceptions end**: `supervise_loops` calls a port and stays a step by the rule (Hard rules),
  and `RunStateReader` reads what `set_shutdown_requested` writes (Naming). Both sentences go, block 160.
- **C3. A parameter object only for values that form a concept** (`Interval`, `FileKey`, `BackoffPolicy`); never a
  bag of dependencies: a component receives each dependency through its constructor, is split by responsibility,
  and holds its state in its own attributes. Hard rules, beside "an adapter receives from the composition what it
  drives", block 310 (the last bag goes).
- **C4. The domain writes plain text; the Markdown is the adapter's**: a notification is a typed value the notifier
  writes out. Hard rules, block 220.
- **C5. A domain object carries who produced it**: a Writer takes the object only (`record_observation(observation)`,
  `record_decision(dated_decision)`, `record_points(points)`); `node_id` is a parameter only as a read's filter.
  Naming, the Writer paragraph, block 252.
- **C6. "A broken input raises" reaches the crawler**: its `validate-config` joins the three tools in the Hard
  rule's list. Block 40.

### Config

- **D1.** A walk over the parsed document resolves `${NAME}` before the domain sees it; the error keeps today's key
  path format (`observability.notifications[0].url`). A mapping's keys are not resolved: they name the schema. A
  resolved value stays a string, so a number cannot come from the environment (`docs/migration-4x.md` says so).
  The operator's choice is A13's option a; resolving everywhere is its price, named in appendix B. In block 20 the
  checks also stop calling `interpolate` and carry their key path apart from their message.
- **D2.** `domain/crawler_config.py` holds `CrawlerConfig`, `LoadedConfig` and the checks; `AMULE_CLIENT_NAME` joins
  `config_defaults.py` in block 20 (Corrected: in block 20, as appendix A's row says, not 30); `time_between_source_reads` moves with `DownloadConfig`, so A2's "time between reads
  computed by the domain" is met here; `math` joins `domain-imports.yml`. The matching parses `matcher.yml` in its
  domain the same way (A13). This supersedes the ledger's A9 config half ("`ConfigError` internal to the config
  adapter, no change"): once the domain builds the config, it raises its own error, and two types for one refusal
  would be the duplication A9 named. `load_config`, which reads the three files, stays in the adapter, its `except`
  following, and its two tests stay in the adapter's test file (Corrected: four, block 20 having added two). Block 30 moves the rest of the code and of its
  819-line test file verbatim: mechanical, exempt.
- **D3.** `ValidateConfig` returns a `ConfigReport` holding at most one `ConfigProblem(file, key, message)`, which
  the command line words. An absent, unreadable or non-YAML file, or one whose root is not a mapping, raises
  `BrokenInputError` (the three tools' name), printed on one line, exit 1: a root that is no mapping is not the
  format the parser reads, as the tools class it. The crawl keeps raising. The split needs D2's. Accepted limit
  (R6): one problem, the parser stopping at the first. `InvalidConfigError` carries its `key` and `message` apart (Corrected: from block 30, which replaces `ConfigError` and so keeps block 20's key path),
  its text staying `<key>: <message>` so the crawl's line is unchanged; the use case adds the `file` it checked.
  `ConfigProblem.key` is `str | None`: `None` for a matching problem, which keeps its whole text as its message,
  since the crawler's 23 config errors name a key path but 39 of the matching's name none apart (`reference cycle:
  a -> b`, `rule 'x' without a condition`), and rewording them is outside this lot. (Corrected: 6 of the crawler's
  errors name their key inside their text, a removed or moved key, a missing root key, a section that is no
  mapping, the backoff's factor and its cap below its base; they carry `key=None` too, so the crawl's line stays
  unchanged.)

### Merge, errors, fixed values, composition

- **D4.** `MergeCatalogs` compares the paths the finder resolved, refuses before any write a new destination
  (`--output`, forced or not) that is also a source, pointing at `--into`, and hands the copier only the sources to
  copy; `destination_is_source` goes. The copier receives each source as the operator spelled it, so its `%s
  merged` line is unchanged; only the use case compares resolved paths. The `skipped: it is the output` line keeps
  its text under the use case's logger (settled, not asked: `docs/operate.md` quotes it). The operator chose A10's
  option b.
- **D5.** A refused read of the downloads, the sources or the status raises `ReadRejectedError` (in
  `domain/client_errors.py`, beside `SearchFailedError` and `DownloadRejectedError`); `ApiRejectedError` stays
  inside the adapter and inherits no port error; the download cycle catches `ReadRejectedError` on its two reads.
  The line `download daemon unreachable (...)` keeps its text. The two integration suites that catch
  `ApiRejectedError` follow (CI only). This is A9's client half.
- **D6.** One engine is shared by the crawl and the webui's thread, which is safe since the engine keeps no state
  after its construction (A15).
- **D7.** Only the four listing use cases read `PAGE_SIZE`, and `application/`'s root holds only the lifecycle (A11).
- **D8.** Settled by H6's rule (R11): the amuleapi page size, the two join timeouts (Prometheus, uvicorn), the SQL
  console's progress step, and the search progress poll interval (`_POLL_INTERVAL`, which the inventory missed, by
  the same rule) become composition constants passed in. `_START_SPACING` stays in the adapter: a network rule, not
  a setting, by its comment. The composition passes `MatchingEngine`'s `max_filename_length` explicitly (settled by
  the Hard rule "the composition passes the real value, never a parameter's default").
- **D9.** `PosixProcess` only installs and removes its signal handlers, nested so the resources close before the
  handlers go; the best-effort close that never masks the first error moves with its test into the composition
  (A12).
- **D10.** The step `resume_backoff_waits` runs beside the node id and the policy check (A6). `SearchTaskRunner`
  takes its saved baseline when its run starts, after the load, so the first search rewrites nothing it just read.

### Types where strings were

- **D11.** `WakeSubject` (`DOWNLOAD`) lives in `domain/wake_subject.py`; the adapter keeps one event per subject, and
  `test_subjects_are_independent` goes, since the type forbids its case (the operator, a; A14).
- **D12.** `catalog_matching/domain/decision_tier.py` holds its three members with `rank` (replaces `TIER_RANK`) and
  `identifies_target` (false for `CATALOG`); `Rule.tier`, `MatchDecision.tier` and `DecisionRecord.tier` take it;
  the values stay the strings of `matcher.yml`, the rows and the metrics. A8's decision: the order and the catalog
  rule held by the type. Block 90 for the matching, 100 for the crawler.
- **D13.** The operator chose A8's option c. `Retraction(target_id)` and `FileTargetDecision = DecisionRecord |
  Retraction` live in `domain/file_target_decision.py`, which absorbs `retraction.py` (`RETRACTED_TIER` goes). The
  column value and the metric label stay `retracted`, written by the decision store and the policy.
  `DecisionChange` carries `previous_decision: FileTargetDecision | None` and `new_decision: FileTargetDecision`,
  and the policy writes `retracted` for a `Retraction` in its log line and metric label, since a field typed
  `DecisionTier` cannot hold a retraction and a persisted retraction can be the previous decision.
- **D14.** `TargetCoverageStatus` (`FOUND`, `PARTIAL`, `NONE`) types the coverage status; the catalog rule's four
  sites (`coverage.py`, two in the webui, the SQL's `tier != 'catalog'`) read `identifies_target`, the SQL generated
  from the type as `_tier_rank_case` already is; the facet order reads `rank`. `/files?tier=` ignores an unknown
  value (settled, not asked: the route's convention for `sort` and `direction`).
- **D15.** The SQL already drops `retracted` (A5).
- **D16.** `records_to_write(fresh, persisted) -> tuple[FileTargetDecision, ...]` in `file_target_decision.py`; the
  step keeps the loop of writes, one clock read per write ("a store has no clock") (A7).

### Source points

- **D17.** The operator chose A2's option a. `ContactPoint` and `parse_contact_point(network, text) -> ContactPoint |
  None` live in the domain; `SourceReading.contact_point: ContactPoint | None`; the mapper builds it; the store's
  guard and its `PersistenceError` path go. Nothing changes for an operator: the mapper already drops an invalid one.
- **D18.** Settled by intent (A2). The step reads the previous point (`read_latest_point(file, reading, since,
  before, node_id) -> LatestPoint | None`, `LatestPoint(role, observed_at, session_received_bytes)`), and
  `carried_role(latest, reading)` decides, the session reset rule included; the step drops a reading with neither
  source nor name, and writes `SourcePoint(file, reading, role, observed_at, node_id)`s through
  `record_points(points) -> None`; `read_earlier_points` returns `LatestPoint`s and `EarlierPoints.of` reduces
  them. One type for both reads (the operator's decision), so `_EARLIER_POINTS` is extended to fetch each variant's
  latest earlier point's `session_received_bytes` beside its instant; the cost is one more seek per variant on the
  same `(variant_id, observed_at)` index, to read the row the `MAX` finds. The store drops the variants with no
  earlier point, as it filters them today. The step reads every previous point before the one write, with no
  `await` between, which keeps today's atomicity (one writer on the event loop). Block 140: the reduction and the
  query; block 150: the roles, `record_points(points, node_id)` for now; block 155: `SourcePoint.node_id`,
  `record_points(points)`.
- **D19.** The step sets the loss deadline after `record_queued` unconditionally, since `is_tracked` precedes it with
  no `await` between. The source half of R7 is D18's.

### Run state

- **D20.** The operator chose A1's option a: `is_paused`, `is_shutdown_requested`, `wait_until_resumed`,
  `wait_until_shutdown_requested`. The predicates may be called from any thread (the webui reads `is_paused`), the
  waits on the crawler's loop only, as the port's docstrings state. The loops, the search tasks, `supervise_loops`
  and the lifecycle receive the port, no `asyncio.Event`; `Event` leaves `core-import-names.yml` (settled, not
  asked: the list states what the core reaches, as the audit's docs commit `7a976c82` removed the unused `enum`
  from `ports-imports.yml`), and block 160 rewords the rule's `note`, whose example is `asyncio.Event`. The ast-grep
  rule `reader-verbs` holds C1 over every driven port's file, as `writer-verbs` holds the Writers' verbs: the
  operator's enforcement order puts a gate tool before a convention, and every Reader method passes it today (35
  `read_`, 2 `is_`, 1 `has_`, 1 `iter_`). With C1 and C2.

### Observability

- **D21.** The operator chose A3's option b. `ObservabilityDispatcher.dispatch(event)` in
  `steps/observability_dispatcher.py` plans the event, logs through `Logger`, applies the metrics through
  `MetricsRecorder` and notifies through `Notifier` under its timeout, absorbing a notifier's failure. Steps call it
  directly; `EventEmitter`, `FakeEventEmitter` and `FakeTimedEventEmitter` go, and the steps' tests assert through
  the real step over `FakeMetricsRecorder`, `FakeNotifier` and `FakeLogger` (about 140 assertions, as
  cosmicpython's message bus is tested). `asyncio.wait_for` joins `core-import-names.yml`. Interim: in block 180
  the step also implements `EventEmitter`, which block 200 removes; `dispatch` takes `node_id` until block 252.
- **D22.** The operator chose a. The step maps each `Severity` to a method by an exhaustive match, `SUCCESS` to
  `info`.
- **D23.** A3 and R6c. The event lines then log under the step's module (appendix B). Block 170 for the names, 180
  for the logger.
- **D24.** A4. `Notifier.notify(audience, notification)`, `Notification = TierRise | SourceAlert | CompletedDownload
  | RelayedLogLine`, with `TierRise(tier, targets, filename, size_bytes, ed2k_link, node_id)`, `SourceAlert(kind,
  source, source_name, absent_for, targets, filename, node_id)`, `SourceAlertKind` (`FIRST_USEFUL`, `REAPPEARED`)
  and `CompletedDownload(targets, filename, node_id)` (the operator: the completed download notifies the community
  today, so by A4's intent it gets a typed kind). The headings, the sections, the backtick escape and the MiB format
  move to `AppriseNotifier`, and with them their tests' expectations, unchanged. The domain keeps the short hash and
  the state phrase for its log line and the adapter repeats them: an accepted duplication, since the log line is
  plain text and the notification its Markdown form. A community kind's notify type is fixed per kind (`INFO` for a
  rise and a source alert, `SUCCESS` for a completed download), so the adapter maps it, a formatting choice like the
  Discord colour. With C4.
- **D25.** The operator chose b. `RelayedLogLine(message, severity, node_id)` has no text of its own, and apprise
  sends the plan's log line unchanged, as today. Block 210 changes the port and relays the six operations events;
  the community notifications cross that block as an interim text notification (the domain's title and body, as
  today), which block 220 replaces by D24's kinds.

### The node on the object

- **D26.** A17. `FileObservation.node_id` (the column exists, no migration), written by
  `record_observation(observation)` (block 230); `DatedDecision` carries its file and a `FileTargetDecision`,
  written by `record_decision(dated_decision)`, into which `record_retraction` merges (block 240; settled by
  "Writers take the object only", not asked); an event whose plan notifies carries its `node_id`, the community ones
  in block 250, the operations ones in block 252, where `dispatch(event)` loses its parameter. A17's "the events
  carry theirs" applies to the events that notify: the seven that feed only the log and the metrics
  (`SearchExecuted`, `SearchFailed`, `ClientUnreachable`, `ObservationRecorded`, `ChannelStatusSampled`,
  `DownloadQueued`, `FreeSpaceSampled`) gain no `node_id`, since the dispatch passes the node to the notification
  only, so nothing would read it there (workflow, "Coherent alone": nothing a block adds is unreachable) (the lead).
  The cut estimate's fourth A17 block is no longer a block of its own: its content went to block 155
  (`SourcePoint.node_id`, `record_points(points)`), blocks 210 and 220 (`notify` without `node_id`, the notification
  carrying its node) and blocks 250 and 252 (`dispatch(event)`). Block 252 also writes C5.

### Dependency bags

- **D27.** The operator chose c. `SearchWorker` receives its dependencies directly (block 260); `StatusLoop.run()`
  (270); the download cycle splits into `DownloadTracker` (follows amuled's list: states, completions, presence,
  loss; owns the loss deadlines; keeps its per-step `StoreError` isolation), `DownloadDecider` (applies
  `decide_download`, writes `queued` on `DOWNLOAD`, owns the disk-low edge), `DownloadStarter` (makes amuled hold
  every queued or downloading download it does not list) and `SourceWatcher` (reads the sources, records the
  points, alerts; owns the sources' read instant), blocks 280 to 300; `DownloadCycle.run()` orchestrates them with
  today's error doctrine and `DownloadLoop.run()` repeats it (310). C3 follows.
- **D28.** Block 10 moves `run_download_cycle.py` verbatim into the modules its classes will have, in `steps/`, and
  its tests into their mirror files, in `tests/application/steps/`:

  | Module | Holds | Test file (tests) |
  |---|---|---|
  | `download_deps.py` | `DownloadDeps` | none (a bag, gone in block 310) |
  | `download_file_reads.py` | `target_titles`, `best_filename` (the reads two stages share) | `test_download_file_reads.py` (2) |
  | `download_tracker.py` | reconcile, completions, presence, loss | `test_download_tracker.py` (22) |
  | `download_decider.py` | `_target_status`, `queue_new_candidates` | `test_download_decider.py` (14) |
  | `download_starter.py` | `start_unlisted` | `test_download_starter.py` (5) |
  | `source_watcher.py` | `_AlertRound`, `_alert_sources`, `record_sources` | `test_source_watcher.py` (15) |
  | `download_cycle.py` | `run_download_cycle`, `_UNAVAILABLE`, the module docstring | `test_download_cycle.py` (16: every arm of the error doctrine, the starvation tests) |
  | `download_loop.py` | `DownloadLoopDeps`, `DOWNLOAD_WAKE_SUBJECT`, `download_loop` | `test_download_loop.py` (6, `git mv` of `test_run_download_cycle_loop.py`) |

  The shared test helpers go to `tests/support/application/steps/download_deps.py`. Nothing else but renames and
  their direct consequences: the eight private names another module now imports lose their underscore; the local
  `target_titles` in `_alert_sources`, which the public name would shadow, becomes `titles`; the shared test
  helpers are renamed where dropping the underscore would collide with a local (`_deps` becomes `build_deps`, `_A`
  becomes `HASH_A`); the wiring test's expected logger name follows the module (`download_loop`), as every logger
  name does since lot B; the importers' lines and `docs/contributing/architecture.md` follow the new paths.
  Mechanical, exempt (the operator). Proved by a dry run on a throwaway worktree (appendix D): no test added,
  removed or duplicated (74 and 6 before and after), `_unit-coverage-check` "0 of 195 modules short of their own
  tests", `uv run poe check` green.
- **D29.** The composition builds each new class and the bag carries it to `run_download_cycle`, losing the fields
  the class took, while the state moves into the classes one stage at a time. Each class logs under its own module.

### Docs

- **D30.** `AGENTS.md`'s glossary (`tier`, `coverage`, `dated decision`, `source point`, `run state`, `wake`, and new
  lines for `retraction`, `notification`, `contact point` and `latest point`), the "Where the code lives" table,
  `docs/contributing/architecture.md`; `docs/migration-4x.md` (French) lists the operator-visible changes of
  appendix B.

### Adapter loggers

- **D31.** The operator's decision (2026-10-23), from the handoff's "For lot C and after" item on amule's adapters
  and C4's adapter form. In `packages/amule/`, `GluetunForwardedPortClient` is the only adapter still receiving the
  `Logger` port from the composition, while `S6ServiceSupervisor` logs through `logging.getLogger(__name__)` since
  lot B's block 94. It takes the same form: its `Logger` parameter goes, the composition stops passing one, and its
  test reads the record's name, as block 94's did. Its logger name is unchanged, already its module's
  (`p2pwatch_amule.adapters.driven.gluetun_forwarded_port_client`), so nothing changes for an operator. About 40
  lines in 3 files, added to block 70's estimate.

### Blocks, in full

| # | Holds | Notes |
|---|---|---|
| 10 | this spec; the download cycle's stages moved verbatim, with D28's renames | 4942 lines, 26 files measured in a dry run; 27 with the architecture doc |
| 20 | the `${NAME}` walk, the checks' key path apart, `AMULE_CLIENT_NAME` | |
| 30 | the config's checks and types to the domain, `ConfigError` replaced by `InvalidConfigError` | |
| 40 | `ConfigReport`, `BrokenInputError`, C6; merge's same-catalog rule | |
| 50 | `ReadRejectedError`; the explainer receives the engine | |
| 60 | `PAGE_SIZE`; the adapters' fixed values, `max_filename_length` | |
| 70 | the resource stack; the backoff waits resumed by the lifecycle; `GluetunForwardedPortClient` logs through `getLogger(__name__)` | D31 adds about 40 lines, 3 files to the estimate |
| 80 | `WakeSubject`; `record_queued` returns nothing | |
| 90 | `DecisionTier` in `catalog_matching` | |
| 100 | the crawler's tiers typed, `Retraction`, `FileTargetDecision`, `DecisionChange` | |
| 110 | `TargetCoverageStatus`, the catalog rule and the SQL from the type, `/files?tier=` | |
| 120 | `CoverageReader`; `records_to_write` | |
| 130 | `ContactPoint` | |
| 140 | `EarlierPoints.of`, `_EARLIER_POINTS` extended to the session's bytes | the query change not in the estimate |
| 150 | `LatestPoint`, `carried_role`, `SourcePoint`, `record_points(points, node_id)` | |
| 155 | `SourcePoint.node_id`, `record_points(points)` | |
| 160 | `RunStateReader`'s predicates and waits, `Event` out of the core's list, `reader-verbs`; C1, C2 | |
| 170 | `ObservabilityPlan`, `plan_observability`, `Logger.debug` | |
| 180 | the dispatch step, implementing `EventEmitter` for now | |
| 190 | the lifecycle, `decisions`, `record_observations`, `reevaluate_catalog` call `dispatch`, their tests through the real step | |
| 200 | the search worker, the status loop and the download stages likewise; `EventEmitter` and its fakes go | |
| 210 | `Notifier.notify(audience, notification)`, `RelayedLogLine`, the interim text notification, each with its node | |
| 220 | `TierRise`, `SourceAlert`, `CompletedDownload` with their node, the Markdown in `AppriseNotifier`; C4 | |
| 230 | `FileObservation.node_id`, `record_observation(observation)` | |
| 240 | `DatedDecision` with its file, `record_decision(dated_decision)` | |
| 250 | `DecisionsRecorded`, `DownloadCompleted`, `SourceFirstUseful`, `SourceReappeared` carry their node, the community notifications built from it | |
| 252 | the six operations events carry their node, `RelayedLogLine` takes it from the event, `dispatch(event)` without `node_id` at its call sites; C5 | |
| 260 | `SearchWorker` without `WorkerDeps` | |
| 270 | `StatusLoop` | |
| 280 | `DownloadTracker`, owning the loss deadlines | |
| 290 | `DownloadDecider`, owning the disk-low edge; `DownloadStarter` | |
| 300 | `SourceWatcher`, owning the sources' read instant | |
| 310 | `DownloadCycle`, `DownloadLoop`, `DownloadDeps` gone, the composition; C3 | |
| 320 | closing block: the holistic findings, backlog, handoff | |

- Thirty-four blocks with the closing one; the operator's ceiling for this lot is 36; the ceiling leaves two blocks
  for the splits Act needs.
- Order: the move (10) first, so every later block edits small modules; the config (20, 30) before R6 (40) and A2
  (time between reads); the tier types (90 to 110) before A5 and A7 (120) and A17's decisions (240); A2 (130 to
  155), A3 (170 to 200) and A4 (210, 220) before A17 (230 to 252); A1 (160) and A3 before the classes (260 to 310).
- Soft spots, in order of risk: blocks 100 and 230 at 19 files; block 252 at 17 files (19 if a caller's test also
  changes); blocks 150, 200 and 220 near the 500-line bound; blocks 280 to 300's re-mapped estimates.

## Appendix B: operator-visible details

- **`${NAME}` reaches every string value of `crawler.yml`** (D1): today only six keys resolve it
  (`amule_api_password`, `catalog_db_path`, `local_db_path`, `webui.amule_url`, a notification's `audience` and
  `url`). A `${NAME}` in any other string value is now resolved too, and an unset variable under any key refuses the
  start, the error naming its key path as today (`search.keywords[0]: environment variable 'X' referenced but not
  set`). A number cannot come from the environment: `${PORT}` under a numeric key resolves to a string, still
  refused as not a number. `targets.yml` and `matcher.yml` are unchanged.
- **`merge` refuses an `--output` that is also a source** (D4), before any write, exit 2, with a message pointing at
  `--into`. Today the unforced case says `destination already exists` and the forced one merges the output into
  itself. The `skipped: it is the output` line of `--into` keeps its text; it is logged by
  `p2pwatch.application.use_cases.merge_catalogs`, before the first `merged` line.
- **`validate-config` prints a broken file apart from a wrong one** (D3): an absent, unreadable or non-YAML file
  prints `error: <file>: <reason>` on one line, exit 1; a readable file with a wrong content prints `Invalid config:
  <file>: <key>: <message>`, exit 1 (today `Invalid config: <key>: <message>`, the file unnamed; a matching problem
  without its key, D3); a valid config still prints `Config valid`. The crawl's `Invalid config, refusing to start: `
  prefix and its environment-variable message are unchanged.
- **Logger names move** (D23, D28, D29): the event lines and the notification failures leave
  `p2pwatch.adapters.driven.observability.dispatcher` for `p2pwatch.application.steps.observability_dispatcher`
  (`docs/migration-4x.md` follows); the download loop's lines leave `p2pwatch.application.steps.run_download_cycle`
  for `p2pwatch.application.steps.download_loop` in block 10, then for the module of the class that writes them
  (`download_cycle`, `download_tracker`, `download_decider`, `download_starter`, `source_watcher`) in blocks 280 to
  310; merge's skip line, above. Every other name stays.
- **`/files?tier=<unknown>` lists every file** (D14), as an unknown `sort` or `direction` falls back to its default.
  Today it lists none.
- **Unchanged, and checked**: the DEBUG lines keep their level and text (D22); every notification keeps its title,
  body, notify type and tag byte for byte, the operations ones relaying their log line as today (D24, D25); the
  metrics, `p2pwatch_decisions{tier="retracted"}` included; the webui's pages; both databases' schemas (no
  migration).

## Appendix C: acceptance commands

Each check names what it prints on `main`, so it can fail.

1. **No `Event` in the core (A1)**: `git grep -n "asyncio.Event" -- packages/crawler/src/p2pwatch/domain
   packages/crawler/src/p2pwatch/application` prints nothing (5 lines on `main`); an `asyncio.Event()` injected in a
   step fails `uv run poe code-pattern-check`; `git grep -n "until lot C" AGENTS.md` prints nothing (2 on `main`).
   A `def fetch_x(self)` injected in a Reader port fails `uv run poe code-pattern-check` (passes on `main`).
2. **The store decides no role (A2)**: `git grep -nE "carried_role|is_contact_point|\bEarlierPoints\b|>
   reading\.session_received_bytes|nothing could tell it" -- packages/crawler/src/p2pwatch/adapters` prints nothing
   (14 lines of the store and the mapper on `main`: the role carried, the reduction, the session reset rule, the
   drop of a reading with neither source nor name).
3. **The dispatch is a step (A3)**: `adapters/driven/observability/dispatcher.py` and
   `application/ports/driven/event_emitter.py` no longer exist; `git grep -nwE "EventEmitter|describe|Report" --
   packages/crawler/src/p2pwatch` prints nothing (49 lines in 13 files on `main`). Removing one arm of the step's
   `Severity` match fails `uv run poe type-check`.
4. **Notifications, log lines and metrics are unchanged (A3, A4)**: the committed evidence first: block 220's
   `test_apprise_notifier` expectations are the strings `test_policy` asserts on `main`, which its pull request's
   diff shows moved, not edited. Beside it, before block 220's pull request opens, a script (its source in the
   block report, one per side since the APIs differ) sends one event of each type (the seventeen, the notifying
   shapes among them: a rise to notify, a rise to download, both source alerts, a completed download, the six
   operations events) through the whole chain on `main` and on the branch, and prints per event its log level and
   text, its metric instructions (`FakeMetricsRecorder`) and each notification call's title, body, notify type and
   tag (`FakeApprise`); `diff` of the two outputs prints nothing. `git grep -nE
   '\*\*(Targets|File|Source|ed2k)\*\*' -- packages/crawler/src/p2pwatch/domain` prints nothing (6 lines of
   `policy.py` on `main`).
5. **The webui renders the same**: over one fixture catalog (decisions of each tier and a retraction included), the
   HTML of `/`, `/files` and one file's page, fetched on `main` and on the top branch, `diff` to nothing (the
   time-dependent text pinned by the fixture's clock).
6. **The lifecycle loads the backoff (A6)**: `git grep -n "load_from" -- packages/crawler/src/p2pwatch/composition`
   prints nothing (1 on `main`).
7. **The tiers are typed (A5, A7, A8)**: `git grep -nwE "TIER_RANK|TIERS|RETRACTED_TIER|_FACET_TIER_ORDER" --
   'packages/*/src/**'` prints nothing (34 lines on `main`); `git grep -nE "tier (!=|==)
   ['\"](catalog|notify|download)['\"]" -- 'packages/crawler/src/**.py'` prints nothing (8 lines on `main`, the SQL
   filter and the webui's two among them); a webui test asks `/files?tier=bogus` and gets every file (none on
   `main`).
8. **The client errors (A9)**: `git grep -n "class ApiRejectedError(ApiError):" --
   packages/crawler/src/p2pwatch/adapters/driven/amule_api/errors.py` prints one line (none on `main`, where it also
   inherits `SearchFailedError` and `DownloadRejectedError`); each of `search`, `start`, `downloads`, `sources` and
   `status` has a test that a refusal raises its operation's port error (`SearchFailedError`,
   `DownloadRejectedError`, `ReadRejectedError` for the three reads), named in block 50's report; CI's integration
   suites pass on the top branch.
9. **Merge (A10)**: `git grep -n "destination_is_source" -- packages/crawler` prints nothing; `python -m p2pwatch
   merge --output a.db --force a.db b.db` exits 2 and leaves `a.db`'s hash unchanged (exit 0 and `a.db merged` on
   `main`).
10. **The small moves (A11, A12, A15, R11)**: `domain/paging.py` no longer exists; `git grep -n "AsyncExitStack" --
    packages/crawler/src/p2pwatch/adapters` prints nothing (3 lines of `posix_process.py` on `main`); `git grep -n
    "MatchingEngine(" -- packages/crawler/src` prints one line (2 on `main`), passing `max_filename_length`; `git
    grep -nE "^_(PAGE_SIZE|POLL_INTERVAL|JOIN_TIMEOUT_SECONDS|PROGRESS_INSTRUCTIONS) =" --
    'packages/crawler/src/p2pwatch/adapters/**'` prints nothing (5 on `main`).
11. **`${NAME}` everywhere (A13)**: with `c.yml` a copy of `deploy/crawler.yml` whose `keywords` read
    `["${P2PWATCH_UNSET}"]`, `AMULE_API_PASSWORD=x uv run python -m p2pwatch validate-config --config c.yml
    --targets deploy/targets.yml --matcher deploy/matcher.yml` prints `Invalid config: c.yml: search.keywords[0]:
    environment variable 'P2PWATCH_UNSET' referenced but not set`, exit 1 (`Config valid` on `main`);
    `adapters/driven/config/errors.py` no longer exists.
12. **The wake subject (A14)**: `git grep -n "DOWNLOAD_WAKE_SUBJECT\|wake(\"" -- packages/crawler` prints nothing
    (32 lines on `main`).
13. **The node on the object (A17)**: in `packages/crawler/src/p2pwatch/application/ports/driven/`, `git grep -n
    "node_id: str" -- observation_writer.py decision_writer.py source_point_writer.py notifier.py` prints nothing (5
    lines on `main`); `NodeIdWriter.record_node_id` keeps its parameter, the node id being what it records.
14. **`validate-config` (R6)**: with `--config /nonexistent.yml` it prints one line starting `error:
    /nonexistent.yml`, exit 1 (`Invalid config: unreadable YAML file: ...` on `main`);
    `ValidateConfig.validate_config` returns a `ConfigReport`.
15. **Writers return nothing (R7)**: `git grep -nE "\) -> (bool|tuple)" --
    'packages/crawler/src/p2pwatch/application/ports/driven/*_writer.py'` prints nothing (2 on `main`).
16. **No bags (the handoff's D8, D27)**: `git grep -nwE "deps|\w+Deps" -- packages/crawler/src
    packages/crawler/tests` prints nothing (138 lines in `src` and 208 in `tests` on `main`);
    `steps/run_download_cycle.py` no longer exists.
17. **Nothing out of scope**: `git diff --stat main...<top branch>` over `deploy/`, `security/`,
    `packages/crawler/src/p2pwatch/adapters/driven/persistence_sqlite/migrations/`, both Dockerfiles and
    `.github/workflows/` prints nothing.
18. **No adapter receives the `Logger` port (D31)**: `git grep -ln "logger: Logger" --
    'packages/*/src/*/adapters/**'` prints nothing (1 file on `main`, `gluetun_forwarded_port_client.py`).
19. **The gate is green** at every block.

## Appendix D: measurements

Taken on `main` at `114f335e` on 2026-10-23 (inventories `inventory-runtime.md`, `inventory-rules.md` and the cut
`cut-estimate.md` in the lead's scratchpad; the probes below by the spec's author). Re-run before acting on one.

- Block estimates: a Sonnet agent on `main` at `114f335e`, a move counted as deleted and added unless git detects
  it. Rows 280 to 300 re-map that estimate's three stage blocks to the operator's class names and are not
  re-measured; rows 150, 155, 210, 220, 250 and 252 come from a second Sonnet estimate after the spec's review.
- Second estimate, after the spec's review (`reestimate-150-250.md` in the lead's scratchpad): block 150 with the
  point's node at 470 lines, 15 files, so the node splits into 155 (110, 9); 210 at 330, 9 and 220 at 410, 10 with
  the notifications' node; the old 250 (every event and `dispatch(event)`) at about 570 lines, 24 files, split by
  who reads the node into 250 (community events, 230, 13) and 252 (operations events and `dispatch(event)`, 240,
  17). Its third part (the seven log-only events, 120, 11) is dropped with their field (D26).
- Block 10's dry run (`block10-dryrun.md` and its scripts in the lead's scratchpad; worktree commit `db3d94c9`,
  thrown away): 4942 changed lines, 26 files against `main` (27 with `docs/contributing/architecture.md`, not done
  in the run); `src` 1159 lines, `tests` 3783, git detecting only the loop test's move. `_unit-coverage-check`
  printed "0 of 195 modules short of their own tests"; moving `test_emits_download_completed` out of
  `test_download_file_reads.py` made it print "1 of 195", so the check sees the new modules.
- `run_download_cycle.py` 546 lines; its tests `test_run_download_cycle.py` 1789 and `_loop.py` 162;
  `crawler_config.py` 521, its test 819.
- `asyncio.Event` in the core: 5 lines; `deps` or `*Deps` in `src`: 138 lines (`git grep -c`).
- Reader methods across every package's driven ports: 35 `read_`, 2 `is_`, 1 `has_`, 1 `iter_`.
- Config errors: 23 `raise ConfigError(` in `crawler_config.py`, 39 raises in `catalog_matching`'s `validation.py`.
- Keys resolving `${NAME}` today: the six of `_string`'s callers.
- Probes: `merge --output a.db a.db b.db` exits 2 (`destination already exists`), with `--force` exits 0 logging
  `a.db merged`; `validate-config --config /nonexistent.yml` prints `Invalid config: unreadable YAML file: ...`,
  exit 1; an unset `${NOPE}` in `amule_api_password` prints `Invalid config: amule_api_password: environment
  variable 'NOPE' referenced but not set`.
- Fixed values in the crawler's adapters: `_PAGE_SIZE`, `_POLL_INTERVAL`, `_START_SPACING` (amuleapi), two
  `_JOIN_TIMEOUT_SECONDS`, `_PROGRESS_INSTRUCTIONS`.

## Appendix E: names

The names the Discuss settled:

| Row | Names |
|---|---|
| A1 | `RunStateReader.is_paused`, `is_shutdown_requested`, `wait_until_resumed`, `wait_until_shutdown_requested` |
| A2 | `ContactPoint`, `parse_contact_point`; `LatestPoint`; `carried_role(latest, reading)`; `SourcePoint` (replaces `RecordedReading`); `EarlierPoints.of`; `SourcePointReader.read_latest_point`, `read_earlier_points`; `SourcePointWriter.record_points` |
| A3 | `ObservabilityDispatcher.dispatch(event)` in `steps/`; `ObservabilityPlan`, `plan_observability`; `Logger.debug` |
| A4 | `TierRise`, `SourceAlertKind`, `SourceAlert`, `CompletedDownload`, `RelayedLogLine`, `Notification`, `Notifier.notify(audience, notification)` |
| A6 | `resume_backoff_waits` |
| A7, A8 | `DecisionTier` (`rank`, `identifies_target`), `Retraction`, `FileTargetDecision` in `domain/file_target_decision.py`, `records_to_write`, `TargetCoverageStatus` |
| A9, A13, R6 | `ReadRejectedError`; `domain/crawler_config.py`; `InvalidConfigError` raised by the domain; `BrokenInputError`; `ConfigProblem`, `ConfigReport` |
| A11, A14 | `application/use_cases/paging.py`; `WakeSubject` in `domain/wake_subject.py` |
| Handoff's D8 | `DownloadTracker`, `DownloadDecider`, `DownloadStarter`, `SourceWatcher`, `DownloadCycle.run()`, `DownloadLoop.run()`, `StatusLoop.run()` |

Names this spec settles by a rule, for the operator to contest: the modules of D27's classes after their class (as
every adapter and port file); `catalog_matching/domain/decision_tier.py` (as `wake_subject.py`);
`steps/observability_dispatcher.py`; `previous_decision` and `new_decision` (D13).

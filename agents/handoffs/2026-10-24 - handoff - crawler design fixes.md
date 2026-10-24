# Handoff: the crawler's design fixes, lot C of the post-hexagonal corrections

Drafted by block 310 from the lot's block reports (#434 to #472), corrected by the closing block 320 with the holistic
review and blocks 315 and 317's reports (#473, #474).

## State

Tier Spec lot. Spec `agents/specs/2026-10-23-crawler-design-fixes.md` (approved 2026-10-23, with the exemptions of
blocks 10 and 30; the operator raised the lot's ceiling to 36 blocks, then accepted 37 and 38 for blocks 265 and 305,
39 and 40 for blocks 315 and 317, added in Wrap).
It applies the ledger `agents/reference/2026-10-22-post-hexagonal-audit.md`'s rows A1 to A15, A17, R6, R7 and R11 in
the crawler, the previous handoff's D8 (the `*Deps` bags) and its item on amule's adapter loggers (D31).

One stack cut from `main` at `114f335e`, stack #469 on GitHub. Forty blocks with the closing one, pull requests #434 to
#474 and the closing block's: the spec's thirty-four, plus 45 (cut from 40 at 24 files), 65 (cut from 60 at 23
files), 265 (added in Integrate by the operator), 305 (cut from 300 at 645 lines), 315 (added in Wrap from the
holistic review's MAJOR) and 317 (added in Wrap by the operator). The lead also moved work between neighbours: block
100's typing of `DecisionTier` into 110, block 150's writer side into 155, block 160's `reader-verbs` into 170, block
200's first commit into 190.

| Block | Pull request | Branch |
|---|---|---|
| 10 | #434 | `refactor/download-cycle-split` |
| 20 | #435 | `refactor/config-interpolation-walk` |
| 30 | #437 | `refactor/config-to-domain` |
| 40 | #438 | `refactor/validate-config-report` |
| 45 | #439 | `refactor/merge-rule-and-config-error-keys` |
| 50 | #440 | `refactor/client-read-errors` |
| 60 | #441 | `refactor/fixed-values-to-composition` |
| 65 | #442 | `refactor/fixed-values-servers-and-console` |
| 70 | #443 | `refactor/composition-resource-stack` |
| 80 | #444 | `refactor/wake-subject` |
| 90 | #445 | `refactor/decision-tier` |
| 100 | #446 | `refactor/retraction-type` |
| 110 | #447 | `refactor/tier-rules-from-type` |
| 120 | #448 | `refactor/coverage-tiers-and-records-to-write` |
| 130 | #449 | `refactor/contact-point` |
| 140 | #450 | `refactor/earlier-points-in-domain` |
| 150 | #451 | `refactor/source-roles-in-domain` |
| 155 | #452 | `refactor/source-point-node` |
| 160 | #453 | `refactor/run-state-waits` |
| 170 | #454 | `refactor/observability-plan` |
| 180 | #455 | `refactor/dispatch-step` |
| 190 | #456 | `refactor/dispatch-from-lifecycle-and-decisions` |
| 200 | #457 | `refactor/dispatch-from-loops` |
| 210 | #458 | `refactor/relayed-log-line` |
| 220 | #459 | `refactor/typed-notifications` |
| 230 | #460 | `refactor/observation-node` |
| 240 | #461 | `refactor/dated-decision-writes` |
| 250 | #462 | `refactor/community-events-carry-node` |
| 252 | #463 | `refactor/operations-events-and-dispatch` |
| 260 | #464 | `refactor/search-worker-dependencies` |
| 265 | #468 | `refactor/file-judge-and-cataloguer` |
| 270 | #465 | `refactor/status-loop-class` |
| 280 | #466 | `refactor/download-tracker` |
| 290 | #467 | `refactor/download-decider-and-starter` |
| 300 | #470 | `refactor/source-watcher` |
| 305 | #471 | `refactor/source-watcher-class` |
| 310 | #472 | `refactor/download-cycle-class` |
| 315 | #473 | `refactor/lifecycle-dependencies` |
| 317 | #474 | `refactor/step-classes-convention` |
| 320 | closing | `docs/crawler-design-fixes-wrap` |

Not merged at writing. The lot changes the image's code (logger names, `validate-config`'s and `merge`'s output,
`${NAME}` everywhere), so a release may follow, after "A copy before a migration that rewrites rows" ships.

## What was built

- **The download cycle split** (block 10, D28, mechanical): `run_download_cycle.py` moved verbatim into its stages'
  modules under `steps/`, its tests into their mirror files; 74 + 6 tests before and after.
- **The config** (blocks 20 to 45, D1 to D4, C6): the config adapter resolves `${NAME}` in every string value
  (`interpolate_document`); `domain/crawler_config.py` checks and builds `CrawlerConfig`, raising
  `InvalidConfigError(key, message)`, every crawler config error carrying its key apart; `ValidateConfig` returns a
  `ConfigReport` of at most one `ConfigProblem(file_path, key, message)` and raises `BrokenInputError` on an absent,
  unreadable, non-UTF-8 or non-YAML file or a root that is no mapping; matching's `int()`/`float()` refuse a bad
  number without a traceback; `MergeCatalogs` alone holds the same-catalog rule and raises `OutputIsSourceError`.
- **Errors, fixed values, composition** (blocks 50 to 70, D5 to D10, D31): each amuleapi method raises its own
  operation's port error through `_refusal_as(port_error)`, a refused read `ReadRejectedError`; `ApiError` derives
  from no port error; `MatchingExplainer` receives the composition's engine; `PAGE_SIZE` in
  `application/use_cases/paging.py`; amuleapi's page size and progress poll interval, both servers' join timeouts,
  the console's `budget_check_instructions` and the engine's `max_filename_length` (no default left) are composition
  constants; the composition owns `resource_stack`, `PosixProcess` only the signals; the step `resume_backoff_waits`
  runs in the lifecycle; `GluetunForwardedPortClient` logs through `logging.getLogger(__name__)`.
- **Types where strings were** (blocks 80 to 120, D11 to D16, D19): `WakeSubject`; `record_queued` returns nothing;
  `DecisionTier` (a `StrEnum`, `rank`, `identifies_target`) in `catalog_matching`; `Retraction` and
  `FileTargetDecision`; `TargetCoverageStatus`; the SQL's catalog rule generated from the type; `/files?tier=bogus`
  ignored; `CoverageReader` and the tier filters typed; `records_to_write` in the domain.
- **Source points** (blocks 130 to 155, D17, D18, D26): `ContactPoint(network, server)` built only valid;
  `LatestPoint`, `EarlierPoints.of`, `carried_role(latest, reading)` in the domain; `SourcePoint` with its node,
  written by `record_points(points)`; the store decides no role and reduces nothing.
- **Run state** (blocks 160, 170, D20, C1, C2): `RunStateReader.is_paused`, `is_shutdown_requested`,
  `wait_until_resumed`, `wait_until_shutdown_requested`; no `asyncio.Event` in the core; the ast-grep rule
  `reader-verbs`; both lot-C exceptions gone from `AGENTS.md`.
- **Observability** (blocks 170 to 220, D21 to D25, C4): `ObservabilityPlan`, `plan_observability`, `Logger.debug`;
  the step `ObservabilityDispatcher.dispatch(event)` replaces the adapter and `EventEmitter`; `Notifier.notify(audience,
  notification)` with `Notification = TierRise | SourceAlert | CompletedDownload | RelayedLogLine`; the Markdown moved
  to `AppriseNotifier`; `Severity` in `domain/observability/severity.py`.
- **The node on the object** (blocks 230 to 252, D26, C5): `FileObservation.node_id`, `DatedDecision` (generic over
  `FileTargetDecision`) written by `record_decision(dated_decision)`, the notifying events carry their node,
  `dispatch(event)` has no `node_id`; no Writer and no notifier method takes `node_id`.
- **No dependency bags** (blocks 260 to 310, D27, D29, C3): `SearchWorker`; `FileJudge.rejudge` and
  `Cataloguer.catalog`, each built once (Seemann's Facade Services, the operator's request); `StatusLoop`;
  `DownloadTracker` (owns the loss deadlines); `DownloadDecider` (owns the disk-low edge) and `DownloadStarter`;
  `DownloadLabeler` (the two reads that name a download, the operator's addition); `SourceWatcher` (owns the sources'
  read instant); `DownloadCycle.run(node_id)` over the four stages with the error doctrine, `DownloadLoop.run(node_id)`
  repeating it. `DownloadDeps` and `DownloadLoopDeps` are gone; C3 is in `AGENTS.md`'s Hard rules.
- **The lifecycle's steps** (blocks 315, 317, C7): `NodeIdResolver.resolve()`,
  `CatalogReevaluator.reevaluate_if_policy_changed(node_id)` (which absorbed the catalog sweep),
  `BackoffRegistry.resume_waits()` and `LoopSupervisor.supervise(loops, ...)` each hold what they use, so
  `CrawlerLifecycle` drops from 17 parameters to 8 and forwards nothing. C7 is a Hard rule: a step is a class, one per
  module, named after it (`backoff_registry.py`, `search_task_runner.py`); the dispatcher's `_log_at_severity` is
  private and `Severity.ERROR`, which no plan produced, is gone.
- **The closing block** (320): the holistic findings below, among them ruff's first-party packages named in
  `pyproject.toml` and the audience derived from the notification (`audience_of`).

## What an operator sees change

As appendix B lists it: `${NAME}` in every string value of `crawler.yml`, an unset one refusing the start under its
key path; `merge` refuses an `--output` that is a source (exit 2, pointing at `--into`); `validate-config` prints
`error: <file>: <reason>` for a broken file and `Invalid config: <file>: <key>: <message>` for a wrong one; the
config errors that named their key inside their text now read `<key>: <message>`, a missing key included
(`search.keywords: missing`, block 320); a crawl that meets a broken file
prints `Invalid config, refusing to start: <file>: <reason>` (block 40); a config file that is not UTF-8 is refused on
one line instead of a traceback (block 40); `/files?tier=<unknown>` lists every file; the event lines log under
`p2pwatch.application.steps.observability_dispatcher`, the download lines under the module of the class that writes
them (`download_cycle`, `download_tracker`, `download_decider`, `download_starter`, `source_watcher`), merge's skip line
under `p2pwatch.application.use_cases.merge_catalogs`, the re-evaluation's under
`p2pwatch.application.steps.catalog_reevaluator` (block 315), the backoff's save failure under
`p2pwatch.application.steps.search_task_runner` (block 317). `docs/migration-4x.md` lists them. No metric, notification,
webui page or schema changes.

## Acceptance

From the block reports; the greps re-run by block 310 at its tip, and by the holistic review at `9556b5a9`.

1. Blocks 160, 170: no `asyncio.Event` in the core, no "until lot C" in `AGENTS.md`; an injected `def fetch_x` fails
   `reader-verbs`, an injected `asyncio.Event()` fails `core-import-names`.
2. Block 155: the acceptance grep over the adapters prints nothing.
3. Block 180, 200: the adapter and `event_emitter.py` gone, `EventEmitter|describe|Report` prints nothing; removing
   the `Severity.ERROR` arm failed mypy (block 317 then deleted `Severity.ERROR`, which no plan produced).
4. Blocks 220 and 252: three scripts send 22 events of all 17 types through the whole chain on `main` and on the
   branch; `diff` prints nothing (90 lines, 26 apprise calls); with the branch's node changed, 13 lines differ.
   Sources in block 220's report. Not re-run after block 252 (blocks 260 to 310 change no event, plan or notifier).
5. Met, by the holistic review at `9556b5a9`: a fixture of five files with decisions of every tier, a retraction,
   several filenames and source points, built with `main`'s stores, rendered by each tree's own `build_app` with a
   fixed wall clock and diffed page by page. 14 pages IDENTICAL (`/`, `/files`, the three tier facets, five file pages,
   `/node`, `/sources`, two target pages); only `/files?tier=bogus` DIFFERS, the intended change (`0 of 0` on `main`,
   `5 of 5` on the branch). Scripts: the session scratchpad's `accept5/` (`build_fixture.py`, `render.py`, `run.sh`).
6. Block 70: `load_from` prints nothing in the composition.
7. Blocks 90, 110: both greps print nothing; `test_unknown_tier_filter_is_ignored_and_lists_every_file`.
8. Block 50: `class ApiRejectedError(ApiError):` at `errors.py:28`; one test per operation asserting the exact type.
   The integration suites: CI.
9. Block 45: `merge --output a.db --force a.db b.db` exits 2, `a.db`'s sha256 unchanged.
10. Blocks 50 to 70: every grep at its expected count (`MatchingEngine(` one line, passing `max_filename_length`).
11. Blocks 20, 40: `Invalid config: <cwd>/c.yml: search.keywords[0]: environment variable 'P2PWATCH_UNSET' referenced
    but not set`, exit 1.
12. Block 80: prints nothing.
13. Blocks 155, 210, 230, 240: prints nothing.
14. Block 40: `error: /nonexistent.yml: No such file or directory`, exit 1.
15. Block 155: prints nothing.
16. Block 310: `git grep -nwE "deps|\w+Deps" -- packages/crawler/src packages/crawler/tests` prints nothing (138 and
    208 lines on `main`); `run_download_cycle.py` gone since block 10.
17. Block 310: `git diff --stat main...HEAD` over `deploy/`, `security/`, the migrations, both Dockerfiles and
    `.github/workflows/` prints nothing.
18. Block 70: prints nothing.
19. The gate green at every block (each report); CI run 40098775950 on `9556b5a9` passed every job, the integration
    suites on both architectures included.

## Holistic review

`.reviews/lot-c-holistic.md` (gitignored), over `git diff origin/main...origin/refactor/download-cycle-class` at
`9556b5a9`: CRITICAL 0, MAJOR 1, MINOR 13. No invariant broken. Each finding's exit, as the operator approved it ("Je
valide le plan"):

| Finding | Exit |
|---|---|
| MAJOR: `CrawlerLifecycle` forwarded 13 of its 17 parameters | fixed in block 315 (8 parameters), C7 in block 317 |
| ruff classes a first-party import by the disk, and its cache keeps the verdict | fixed in 320: `[tool.ruff.lint.isort] known-first-party` names the eight packages and `tests` |
| `ObservabilityPlan.audiences` apart from its notification | fixed in 320: the field dropped, `audience_of(notification)` decides |
| a missing nested config key keyed on its section | fixed in 320: `search.keywords: missing`, `docs/migration-4x.md` updated |
| `AMULE_CLIENT_NAME` among the domain's defaults | fixed in 320: the composition's `_AMULE_CLIENT_NAME`; spec D2 corrected |
| the readers' `'retracted'` literals | fixed in 320: `tier IN (<every DecisionTier>)`, generated from the enum |
| `download_tracker.py`'s `del` after a loss, a surviving mutant | fixed in 320: deleted, the reconciliation owns the drop |
| `async with PosixProcess(...), resource_stack()`'s untested order | fixed by a comment naming the exit order, SIM117 refusing nested statements (which would also re-indent 221 lines); no unit test can reach inside `run_crawler`. The operator's "oui" |
| stale docs: matching's `AGENTS.md` sketch, `mapping.py`, the cataloguer's docstring | fixed in 320 |
| two docstrings of this lot pointing at a bare decision id | fixed in 320; the ones moved verbatim from `run_download_cycle.py` stay |
| `docs/operate.md`'s 147-character line | fixed in 320 |
| `DecisionChange.title` for a gone target reaches no output | accepted limit: the file judge cannot know which change will rise, the policy decides |
| no check that a contact point's network is its file's | `BACKLOG.md`, in the "Stage 5, new networks" entry: with one network the check cannot fail under coverage |
| the handoff's acceptance 5, "Constructor sizes" and later items | corrected here |

## Departures from the spec

- Block 20: `AMULE_CLIENT_NAME` moved here (appendix A's row). Six raise sites first kept `key=None` to keep their
  text; block 45 gave them their key apart by the operator's choice.
- Block 30: `InvalidConfigError(key, message)` here rather than in 40; the four `load_config` tests stay in the
  adapter's test file.
- Block 40: `ConfigProblem.file_path`, not `file` (the glossary keeps `file` for a `FileKey`); the file printed as the
  cwd-joined path.
- Block 50: `ApiError` no longer derives from `ClientError`; the context manager `_refusal_as` (a decorator's body
  runs at import, credited to no test); `test_explainer_engine_cached_across_calls` removed.
- Block 60: `progress_poll_interval`, `_AMULE_API_PAGE_SIZE`, `_AMULE_API_PROGRESS_POLL_INTERVAL`.
- Block 65: `MatchingEngine` loses its default too (the lead), tests pass `_MAX_FILENAME_LENGTH = 4096`.
- Block 70: `Logger.warning` removed from `p2pwatch_amule`'s port, its adapter and its fake (no caller left).
- Block 80: `test_a_duplicate_queuing_keeps_the_deadline_its_latest_seen_at_leaves` and
  `FakeLaggingTrackedDownloadStore` removed (the race D19 declares impossible); the fake's duplicate guard went.
- Block 90: `DecisionRecord.tier` stays `str` until 100; `identifies_target` in 110; `DecisionTier` a `StrEnum`;
  `rank` reads `_WEAKEST_FIRST`.
- Block 100: `record_retraction` kept its signature until 240.
- Block 110: `coverage_of` converted strings until 120; `decide_download` takes a `DecisionTier`; `?tier=` no longer
  stripped of whitespace.
- Block 120: `record_decision` kept `MatchDecision` until 240; block 110's tier filters typed here; an unknown tier
  string raises in the SQLite readers.
- Block 140: `LatestPoint` arrives here, not in 150; a query-cost test warms its statement up first.
- Block 150: `FakeSourcePointStore.read_latest_point` raised until 155; the store's window a `timedelta`.
- Block 180: `log_at_severity(logger, severity, message)` a module function.
- Blocks 190, 200: the node id asserted only on events that notify; `FakeTimedNotifier` replaces
  `FakeTimedEventEmitter`; source alerts asserted by their bodies until 220.
- Block 210: the interim `TextNotification` (gone in 220); the notification types in
  `domain/observability/notification.py`.
- Block 220: `target_titles` fields; `SourceAlertKind` a `StrEnum`, `absent_for` a `timedelta`; `Severity` moved to
  break the import cycle; a rise detected by `identifies_target`.
- Block 240: `DatedDecision[Decision: FileTargetDecision]`, moved to `file_target_decision.py`; two retraction tests
  pruned.
- Block 252: the policy builds the `RelayedLogLine`; `ObservabilityPlan.notification` is a `Notification | None`;
  `CommunityNotification` gone.
- Block 265: `rejudge` and `catalog` take `node_id`, `catalog` takes `client_name` (one `Cataloguer` for every worker).
- Block 280: three tests moved from `test_download_cycle.py` to `test_download_tracker.py`; two tests reading the
  deadlines became behavioural.
- Block 310: the loop test keeps its own stage graph (a first version built it through `build_cycle`, 66 lines more,
  past the 500-line bound).
- Block 315: `LoopSupervisor`, C7 and the `BackoffRegistry` module left to block 317 (the operator).
- Block 317: `log_at_severity` a private method of the dispatcher, `Severity.ERROR` deleted (its class 2 answer).
- Block 320: the resource stack's order named by a comment, not two nested `async with` (ruff's SIM117); the readers
  now drop a tier the enum does not list instead of raising on it; the optional de-duplication of the loop test's
  stage graph not done (the block already past the file bound).

## Class 1 fixes

- Block 40: a config file not in UTF-8 crashed `validate-config` and the crawl with a traceback.
- Block 50: `test_status_loop.py` imported the adapter's errors into a step test.
- Block 90: three crawler tests seeded a retraction through `record_decision`; `retraction.py`'s docstring.
- Block 130: the glossary put the source points in local.db; they are in catalog.db.
- Block 200: `download_cycle.py`'s docstring said "emit".
- Block 220: the observability diagram's `use-case emit(Event, node_id)`.
- Block 240: `sqlite_decision_store.py`'s module docstring.
- Block 305: `FakeBlockingMonotonicClock.now()` raises (`-> NoReturn`), with a guard test.

## Class 2 questions

- Block 45: matching's bare `int()`/`float()` tracebacks, fixed in this lot ("reco ok"); the six errors' key apart
  ("bah oui"); merge's refusal names `--into` through a typed error ("B").
- Block 80: 20 files ("J'autorise le dépassement, simplement"); from then on, one or two files past the bound stay
  whole in this lot.
- Block 160: 22 files ("oui").
- Block 180: 28 files, 17 of them the fakes' mechanical move, kept whole ("oui").
- Block 220: 600 lines, kept whole ("Oui").
- Block 260, in Integrate: Facade Services for the forwarded dependencies ("Oui"), `FileJudge` and `Cataloguer`
  ("Ok"), block 265 with the mechanical exemption, the lot at 37 ("Ok").
- Block 300: `DownloadLabeler` added ("Ok"), then the block cut into 300 and 305, the lot at 38 ("validé").
- Block 315, after the review: the MAJOR fixed by Facade Services, 921 lines exempt, the rest to a block 317, the lot
  at 40 ("ok"); `search_tasks.py` renamed in 317 ("ok").
- Block 317: kept whole at 637 lines and 22 files under a mechanical exemption ("Validé"); `log_at_severity` private
  and `Severity.ERROR` deleted ("Validé").
- Block 320: kept whole at 22 files, with a one-line comment instead of the two nested `async with` ruff refuses
  ("oui").

## Names settled by teammates

`interpolate_document`, `YamlLoadError`, `ConfigProblem.file_path`, `OutputIsSourceError`, `_refusal_as`,
`progress_poll_interval`, `_AMULE_API_PAGE_SIZE`, `_AMULE_API_PROGRESS_POLL_INTERVAL`, `join_timeout_seconds`,
`budget_check_instructions`, `_MAX_FILENAME_LENGTH`, `resource_stack`, `_WEAKEST_FIRST`, `ContactPoint.server`,
`_plan_decisions`, `_plan_source`, `log_at_severity`, `FakeTimedNotifier`, `target_titles` (the notifications'),
`domain/observability/severity.py`, `_relayed`, `_decision_columns`, `track`, `reset_loss_deadline`,
`queue_new_candidates`, `start_unlisted`, `record_sources`, `DownloadLabeler.best_filename`,
`DownloadLabeler.target_titles`, `build_cycle` (the stages' test helper, in `tests/support/application/steps/download_cycle.py`),
`NodeIdResolver`, `CatalogReevaluator`, `resume_waits`, `LoopSupervisor`, `audience_of`, `_AMULE_CLIENT_NAME`,
`_DECISION_TIERS`.

## Backlog

Reconciled by block 320: nothing in it shipped with this lot, so no entry is deleted. "A copy before a migration that
rewrites rows" stays open and comes before any release; "Contract tests for the fakes" follows this lot, the ports now
in their final shape; "The node page shows a node id set in `crawler.yml`" names `NodeIdResolver` (block 315); the
"Stage 5, new networks" entry gains `SourcePoint` refusing a contact point of another network than its file's (the
holistic review, the operator's agreement).

## For the next lots

- **The decider holds the whole `DownloadTracker`** (block 290, weighed in 310 and kept): it calls only
  `reset_loss_deadline(file)` right after each `record_queued`, with no `await` between (D19). The alternative, the
  decider returning the files it queued and the cycle resetting their deadlines, loses the reset of the files queued
  before a `StoreError` mid-loop, which would then fall back on `latest_seen_at` and the wall clock.
- **Constructor sizes** (Seemann's over-injection, checked per block, counted at 320's tip): `CrawlerLifecycle` 8
  parameters, `DownloadDecider` 11, `SourceWatcher` 12, `DownloadTracker` 8, `DownloadStarter` 5, `DownloadLabeler`
  4, `DownloadCycle` 6, `DownloadLoop` 5, `StatusLoop` 7, `CatalogReevaluator` 7, `NodeIdResolver` 5; none passes a
  dependency straight through to one callee since blocks 265, 300 and 315.
- **The loop test builds its own stage graph** beside `build_cycle` (block 310): about 70 lines that blocks 280 to
  305 each edited beside the shared helper. Left by 320, which was past the file bound.
- **Strings a `StrEnum` lets pass** (blocks 110, 120): `test_prod_targets.py` compares `t.status == "found"`, and
  `test_app.py`'s `_decision(tier="catalog")` passes strings; mypy accepts both.
- **A tier the enum does not list** (block 320): the readers keep `tier IN (<every DecisionTier>)`, so a row of an
  unknown tier (a catalog written by a later version) is skipped where `DecisionTier(row["tier"])` used to raise.

## Pitfalls

- **ruff classed a first-party import by whether its module existed on disk** (blocks 210, 220), and its cache kept
  the verdict: tests written before their module sorted it third-party, the local gate passed, CI's cold run failed.
  Fixed by design in block 320 (`known-first-party`): before, a probe printed pass, pass, pass, fail for "absent cold,
  absent warm, present warm, present cold"; after, all four agree.
- **GitHub refuses to change the base of a pull request in a stack** (block 265's insertion): the lead unstacked it on
  GitHub and submitted the stack again, which is why the stack is #469 and block 265 is #468.
- **`gh stack` 0.1.1 inserts a branch mid-stack only through its TUI**: the lead edited `.git/gh-stack` by hand
  (blocks 265, 305).
- **ruff's SIM117 refuses two nested `with` statements** that one could hold (block 320).
- **Serena's `find_referencing_symbols` returns nothing** on a new module, a module constant or `tests/support`
  (blocks 10, 20, 310): `git grep -w` instead.
- **A decorator's body runs at import**, credited to no test by `_unit-coverage-check`, and a decorated `async def`
  types as `Awaitable`, breaking a port override (block 50).
- **A `StrEnum` equals its text**: assert the type with `is`; mypy accepts a literal where the type is expected, so
  grep the callers (blocks 90, 110, 120). `x in DecisionTier` does not narrow `str | None` (block 90).
- **Two small modules rewritten under new names count four files**, git seeing no rename (blocks 100, 265, 300).
- **`git checkout <file>` to revert a probe** discards uncommitted work in that file (block 250); `git checkout -p`
  fed on stdin reverts the hunks in git's order (block 210). Commit before probing.
- **A Bash command a hook refuses never runs**, edits chained in front of it included (block 200).
- **`uv run poe fix` exits non-zero on its first run** when ruff sorts imports; a second run is clean (block 30).
- **`async with A, B` exits B first** (block 70).
- **A `match` over two kinds leaves a partial branch**; an `isinstance` helper covers both sides (block 240).
- **A YAML error loses its snippet** to fit one line (block 40).
- **The `${NAME}` walk has no depth guard**: PyYAML fails first on a document deep enough (block 20, reasoned).

## Not validated

- The integration suites locally; CI runs them (the client errors of block 50, the two new amuleapi arguments of
  block 60 in the compose smoke's script).
- The logger names of `DownloadTracker`, `SourceWatcher` and `DownloadCycle`: no wiring scenario produces their lines;
  the composition passes `StdlibLogger(<Class>.__module__)`. `DownloadDecider`'s is tested (block 290).
- The resource stack's nesting order, shown only by `run_crawler` (block 70), now named by a comment (block 320).

## Wrap counts

Counted by block 320 with `gh run list --branch <branch>` over the 39 branches below it: 60 runs of the `PR` workflow
for 39 pull requests, so 21 beyond one run each.

- **Fix-backs and the runs they re-triggered** (16):
  - block 45's `--into`: the fix on 45, then a cascaded rebase over 50 to 80, 11 runs (one on 45, two on each of the
    five branches above it, one of each pair cancelled by the next push);
  - block 210's two lint fixes, ruff's cache having let the import order pass (`e33d8aaf`, `08924bde`): 2 runs, both
    failing before them, no cascade;
  - block 260's Facade Services, which became block 265 inserted under 270: the stack rebuilt on GitHub and a cascaded
    rebase over 270 to 290, 3 runs.
- **Re-pushes by a block's own teammate before the next block began** (5): blocks 20, 110, 155, 170, and 190, which
  took block 200's first commit.
- **Cascaded rebases**: two (block 45's over five branches, block 265's over three).
- **Bodies called unreadable**: none; the operator called no body unreadable unprompted.
- **The measure**: 16 runs re-triggered by fix-backs and cascades, 21 counting the teammates' own re-pushes, against 40
  blocks. Fewer runs than blocks and no unreadable body: by workflow's measure, stacking cost less than pull requests in
  series.

- **Splits**: 40 into 40 and 45, 60 into 60 and 65, 300 into 300 and 305; work moved by the lead from 100 to 110, 150
  to 155, 160 to 170, 200 to 190.
- **Exemptions**: 10 and 30 (the spec), 180 (28 files), 220 (600 lines), 265 (890 lines, 15 files), 315 (921 lines,
  22 files), 317 (637 lines, 22 files).
- **The file allowance passed**: 320 at 22 files by the operator (139 lines).
- **The file allowance** (20 or 21 files): blocks 80, 90, 110, 120 and 230; block 160 at 22 by the operator.
- **Bodies called unreadable**: none known at writing.

## Next

- The operator reads the stack; the lead rebases it onto the current `main` and waits for every run to be green; the
  operator merges it (`gh stack merge --rebase`).
- After the merge, the lead proposes a release decision: the lot changes what the image ships (logger names,
  `validate-config`'s and `merge`'s output, `${NAME}` everywhere). "A copy before a migration that rewrites rows" still
  gates any release.
- Then "Contract tests for the fakes", the ports now in their final shape.

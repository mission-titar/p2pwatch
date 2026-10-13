# Handoff: an append-only catalog again, sources as points

## State

Tier Spec lot, spec `agents/specs/2026-10-13-append-only-source-points.md` (approved 2026-10-13), which
replaces the draft `2026-10-13-monotone-catalog-ranges.md` (removed in block 10) and corrects stage 4's
D4, D5, D6 and D8. Five blocks, one stack cut from `main` at `ba32bc0`: #193 (10,
`feat/source-observations`), #194 (20, `feat/webui-source-interval`), #196 (30, `feat/sources-interval`),
#197 (40, `docs/append-only-sources`), then the closing block 50 (`docs/source-points-closing`), which
holds the holistic review's fixes, `BACKLOG.md` and this handoff.

Nothing of the stack is merged. `git tag -l 'v*'` still ends at `v4.1.0`; the node runs 4.1.0.
`catalog.db` goes to schema version 11 (`catalog/0011_source_observations.sql`); `local.db` stays at 8.

Once merged, every catalog table is append-only again: a node in download mode writes one point per
source per read, every `download.sources_interval_seconds` (300 s by default), and the webui computes
presence periods from those points at each display, within an interval of at most 7 days.

## What was built

- **The switch** (block 10): migration 0011 drops `source_ranges` and stage 4's `source_variants`, and
  creates D2's `source_variants` (with `node_id`, in its `content_hash` too, and an index on it) and
  `source_observations` (`variant_id`, `observed_at`, `transfer_counter`, `WITHOUT ROWID`), both empty,
  both under the `_no_update` / `_no_delete` triggers. `record_readings(file, readings, read_at)` writes
  a variant (`ON CONFLICT (content_hash) DO NOTHING`) and one point (`ON CONFLICT (variant_id,
  observed_at) DO NOTHING`) per reading, carrying the latest point's group to a passing state within
  the tolerance when its counter is not above the reading's, and returns `RecordedReading`s.
  `earlier_points` and `has_points_before` replace `earlier_ranges` and `has_ranges_before`;
  `OpenedRange` is gone. `merge` copies `source_observations` with `INSERT OR IGNORE`, the variant
  remapped through `content_hash`; the diverged-copy fixture now merges. The webui computes periods in
  SQL with window functions, partitioned per identity, file and node, cut on a change of variant, a gap
  over the tolerance or a counter drop; only a `sending` period counts received bytes. The tolerance is
  `webui.source_period_gap_seconds` (default 990), a reading option in every run mode. `/sources` and the
  pair lists read each variant's latest point instead of aggregating every point.
- **The interval** (block 20): `webui/domain/interval.py` (`requested_interval`, `MAX_SPAN` of 7 days,
  four presets, `shifted` for Previous and Next) and `interval.html`, included by the file, source and
  name pages. One interval per page bounds the period tables and the file page's "Observations"
  timeline, whose read is now a `SEARCH` on `observations`' primary key bounded by `observed_at`.
- **The cadence** (block 30): `download.sources_interval_seconds` (default 300) parsed into
  `DownloadConfig.sources_interval: timedelta`; the sources step runs on the first round after a start,
  then on the first round at least the interval after its last start (`DownloadDeps.sources_read_at`),
  a failed read included. The repository's tolerance is `3 x (sources_interval + poll_interval)`.
  `decision_poll_interval_seconds` joins `_REMOVED_KEYS`.
- **The close** (block 50): the holistic review's eight findings fixed (below): the per-source reads
  kept off the `node_id` index, every duration of `crawler.yml` bounded (a day, or 30 days for an
  absence) by one helper, `_seconds`, the webui's gap named after its
  setting end to end, the byte counter in `legal.md` and `index.md`, the spec approved, with a
  section on the intervals measured on the wall clock.
- **The documents** (block 40): the invariant without stage 4's exception in `AGENTS.md`'s Persistence
  row, `docs/contributing/architecture.md` (§8's diagram and bullet, §11) and
  `adapters/persistence_sqlite/__init__.py`; `architecture.md` §7 (the step's cadence), §8 (schema
  version 11, what 0011 does) and §8.3 rewritten for points, the carried group, the union and the
  computed periods; `docs/operate.md` (the source history in points and periods, the merge paragraph
  without its limit, `expected 11`, the routes within the interval, a new "L'intervalle des pages de
  détail" subsection, alerts up to one interval late); `docs/settings.md` (two sections, one per new
  key); `docs/index.md` (the merge limit gone); `docs/legal.md` (the instant of each read instead of
  "les plages de temps"); `docs/migration-4x.md` (step 3 names `decision_poll_interval_seconds`).

## Decisions taken during Act

- **Class 2, block 50**: `download.poll_interval_seconds` was unbounded, and the writer's spacing adds
  it, so a poll of 4e12 s still raised `OverflowError: Python int too large to convert to SQLite
  INTEGER` in `record_readings` once the source keys were bounded at a year. Operator: "même un an est
  absurde comme limite [...] il faut mettre une borne haute cohérente [...] une limite commune dans un
  helper". One helper reads every duration key with an upper bound, default a day: the poll, the
  sources interval, the gap, `backoff.base_seconds` and `cap_seconds`, `shutdown_deadline_seconds`,
  `notification_timeout_seconds`; 30 days for `lost_after_seconds` and `reappeared_after_seconds`. The
  one-year bounds went; `settings.md` gains "Les bornes des durées".
- **Operator, on #198** (review comment on `crawler_config.py:240`): "`what` est un mauvais nom, pas
  assez descriptif". The config helpers' `what` became `section` (the path prefixing the key in
  errors), `_require_mapping`'s became `label`, and `interpolate`'s became `field`. The operator's
  wider sweep (undescriptive names across the code, a lint rule or an agent guideline) went to
  `BACKLOG.md`, linking that comment.
- **Class 2, block 10**: the webui's tolerance on a crawl-only node, which reads no source. Operator: a
  reading option, `webui.source_period_gap_seconds` beside `webui.enabled`, default 990, in every run
  mode; block 30 hands the spacing to the repository only.
- **Operator, recorded by block 10's spec corrections**: block 30 removes
  `decision_poll_interval_seconds`; block 20 bounds the search timeline, which closes "Paginate the file
  detail timeline"; a backlog entry moves `backoff` under the search config with stage 5.
- **Block 10**: D5 answers in one statement (each variant's latest point before the round, with its
  role, grouped in Python), and a source decided once is not asked again in the round. On the source
  and name pages, the page nav moved under the names list. Budget 1410 lines and 39 files, against the
  spec's 950 and 22; the spec states why this block passes both bounds.
- **Block 20**: `from` missing, unreadable or not before `to` falls back to the 7 days ending at `to`,
  silently; an instant before 1970 is read as absent; presets are absolute links ending at the page's
  render time; the custom form has no `action`; interval links keep `page` only above 1; empty tables
  say "in this interval". Its first measure was 517 lines, brought to 495 by removing domain tests the
  app tests duplicated.
- **Block 30**: the field is `sources_interval: timedelta`, parsed like `reappeared_after` by
  `_duration_default`; the last run lives in `DownloadDeps.sources_read_at`; the tests that used
  `decision_poll_interval_seconds` as a required root number use `shutdown_deadline_seconds`;
  `tests/smoke/crawler.yml` drops the removed key.
- **Block 40**: D9 names `architecture.md` §1, which holds no append-only statement: nothing changed
  there. Beyond D9's list: `migration-4x.md`'s step 3 (the 4.x to 5.0 path is the one an operator will
  take, and a leftover key stops the boot), §7's step cadence, `operate.md`'s alert latency, and a class
  1 fix (below).

## Class 1 fixes

- Block 50: none; the fixes below are the holistic review's.
- Block 10: `adapters/mule_api/mapping.py:40` and `test_mapping.py:552` said "latest range".
- Block 20: the docstrings of `HiddenInput` and `PeriodWindow`.
- Block 40: `domain/observability/events.py`'s `SourceNew` comment said "opened its first useful
  range".

## Spec corrections

Every `(Corrected: ...)` in the spec, applied during Act: section 2 and D6 (the interval also bounds the
search timeline); D3 (the spacing feeds D4 only); D5 (one statement); D6 (the tolerance is
`webui.source_period_gap_seconds`, raised by a merged catalog's operator); section 6 (block 20's size,
block 10's and 30's contents, the transient surfaces, the timeline backlog entry closed, the `backoff`
entry); section 7 (the timeline bound, the removed key, the gap key's criteria); section 8 (the
displaying node's gap). Block 50 adds: the status approved; D2 (the `node_id` index serves
`has_points_before` only); D3, D6 and section 7 (every duration key at most a day, 30 days
for an absence); section 7's D5 criterion
(steps flat against the node's other variants, for D4's carried role too); section 6's block 50 row;
section 8, "Intervals measured on the wall clock".

## Wrap counts

Counted with `gh run list --branch <b> --limit 50 --json databaseId,workflowName,headSha,event,conclusion,createdAt`
on each stack branch, 2026-10-13, before block 50's own run.

- **Fix-backs**: 1. `735679d` on block 30 (a clock stepped back read the sources at once), made at the
  operator's request on block 30's report, then removed at the operator's request in favour of the
  monotonic clock backlog item; block 30 is back at `97423d8`.
- **Cascaded rebases**: 2, both onto block 40: after the fix-back (`97adadc` to `4e38ca3`) and after its
  removal (`4e38ca3` to `c395eae`). #193 and #194 never moved.
- **Runs**: #193 one (`38415800988`, `3fb679b`, green); #194 one (`38417663729`, `4ea3b38`, green). Runs
  the fix-back and the cascades re-triggered: **6**. On #196, `38420445348` (`735679d`, cancelled by the
  removal's push) and `38421021009` (`97423d8` again, green), beside its first green run `38418987173`.
  On #197, two runs per push, the first cancelled by the workflow's concurrency group: `38420442750` and
  `38420444096` (`4e38ca3`, both cancelled), `38421018871` (cancelled) and `38421019263` (`c395eae`,
  green); block 40's first run, `38420030413` (`97adadc`), was cancelled by the first cascade before it
  finished, so block 40 never ran green at its original head.
- **Bodies the operator called unreadable**: none.
- Six runs re-triggered against five blocks: by the workflow's measure, this lot's stacking cost more
  than pull requests in series. Four of the six are the doubled runs on #197, and the fix-back that
  caused both cascades was withdrawn.

## Holistic review

Run by `holistic-source-points` over `git diff origin/main...origin/docs/append-only-sources` at
`c395eae`: CRITICAL 0, MAJOR 1, MINOR 7. Every finding exits as fixed, in block 50 (operator: no other
exit).

| Severity | Finding | Exit |
|---|---|---|
| MAJOR | Without `ANALYZE`, `_LATEST_POINT` and `_EARLIER_POINTS` planned on `idx_source_variants_node_id`, walking every variant of the node (5.5 ms a call at 100,000 variants against 0.007 ms) | Fixed: `+v.node_id` in both; two tests count VM steps with 100 then 10,000 other variants on the node, for `earlier_points` and a passing-state `record_readings`, failing first with `assert 49493 <= (544 // 10)` and `assert 49461 <= (737 // 10)` |
| MINOR | Both new keys accepted values whose derived tolerance overflows (`OverflowError` at composition, or an int64 bind that escaped `run_download_cycle`) | Fixed, widened by block 50's class 2: `_seconds` bounds every duration key at a day (30 days for an absence), with a `ConfigError` naming the key and its bound; one test per family, failing first with `DID NOT RAISE ConfigError` on all nine cases; `settings.md` lists every bound |
| MINOR | Bare "(D4)", "(D4, D6)" read as stage 4's; `source_tolerance`'s docstring named D6; the 300 s default gave no reason | Fixed: the spec named, D6 dropped, the reason inline |
| MINOR | One concept, four names (`source_period_gap_seconds`, `source_period_gap`, `source_tolerance=`, `PeriodWindow.tolerance`) | Fixed: `build_app(source_period_gap=...)`, `PeriodWindow.gap`, the SQL's `:gap` |
| MINOR | "plus `download.poll_interval_seconds`" understated a round (poll plus the cycle) | Fixed in `settings.md`, `_sources_spacing` and the repository's docstring |
| MINOR | `legal.md` and `index.md` omitted the byte counter each point stores | Fixed in both |
| MINOR | The spec's status still read "awaiting" | Fixed: approved on 2026-10-13 |
| MINOR | "Not validated" listed the integration suites, which CI ran | Fixed: below, as validated by CI |

## Pitfalls

- **A node whose `crawler.yml` still holds `decision_poll_interval_seconds` refuses to boot.** The
  release notes must say to delete the line; `docs/migration-4x.md` step 3 does.
- **A `crawler.yml` with a duration above its new bound refuses to boot** (a day, 30 days for
  `lost_after_seconds` and `reappeared_after_seconds`). Every shipped value is far below; the release
  notes should name the bounds.
- **The sources step's gate compares wall-clock times**: a clock stepped back suspends source reads until
  it passes the last start plus the interval again. An accepted limit, with the amuleapi client's pacing
  and deadlines and the persisted search backoff: spec section 8, "Intervals measured on the wall
  clock", and its `BACKLOG.md` item.
- **Without `ANALYZE`, SQLite prefers the `node_id` index** whenever a query filters on `v.node_id = ?`;
  on a single-node catalog it holds every variant. A per-source read writes `+v.node_id`, and a test
  that varies the points only cannot see it: vary the other variants too.
- **The first call of a statement on a connection costs VM steps** the next calls do not: a step-count
  comparison warms the read up first.
- **With strict `<` before `read_at`, a point at the same instant never carries its own role**: that
  is what makes the same read written twice idempotent.
- **The file page shows the latest sighting's name in its eD2k link whatever the interval**: a
  timeline assertion must target `<td>name</td>`.
- **Literal template text is not escaped** (`interval's`), while interpolated text is.
- **The name page's period table holds hashless periods only.**
- **`uv run poe docs-build` fails on a dead anchor** (`Aborted because --strict flag is set`), checked
  again in block 40 with a broken link to `settings.md`'s new section.

## Validated by CI only

The integration suites were not run locally in this lot. CI ran them in `build-and-verify`, on amd64 and
arm64 (`Compose smoke stack integration`, then `API, download and orchestration integration`), green on
#193 (`38415800988`), #194 (`38417663729`), #196 (`38421021009`) and #197 (`38421019263`); block 50's
own run is in its pull request.

## Not validated

- **The webui's period computation on the node's real points**, once the node runs this lot; block 10
  measured 168 ms for 7 days of a seeded 3M-point file in the core image.
- **The timeline's bounded read on the node's catalog**: only its plan is asserted.
- **A source's points per day at 5 minutes** on the node, against the 288 assumed (spec, section 8).
- **The variants' stability**: new `source_variants` per (file, source) per hour without a change of
  role, under 2, once the node runs this lot.
- **The search points per day under stage 2's pace**: `SELECT COUNT(*) FROM observations WHERE
  observed_at >= :since` over a day, against 4.1.0's 124k.
- **The `datetime-local` fields in a real browser**: only the rendered HTML was read.
- Stage 4's carried-over items: a source read against a real amuled, the step's cost inside the cycle,
  a notification on a real apprise target.

## Next

The operator reviews the stack, the lead rebases it onto `main`, and the operator merges. **The lot
changes the image, but the next release waits for section 9's lot**: the node's next upgrade runs stage
1's 0006 to 0009 over its 5.9 GB catalog, and a copy before a migration that rewrites rows is required
first. `BACKLOG.md`, reconciled in block 50, lost "Search observations as time ranges" (dropped, spec sections 4
and 5), "Merge diverged copies of one node's catalog" and "Paginate the file detail timeline" (both
shipped), and gained the copy before a migration (the next lot, required before the release), the webui
in the visitor's time zone, `backoff` under the per-client search config, and the monotonic clock. Once
the node runs this lot, the measures above.

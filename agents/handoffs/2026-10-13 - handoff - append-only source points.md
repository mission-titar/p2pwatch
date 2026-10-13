# Handoff: an append-only catalog again, sources as points

Drafted by block 40, for the closing block 50 to correct.

## State

Tier Spec lot, spec `agents/specs/2026-10-13-append-only-source-points.md` (approved 2026-10-13), which
replaces the draft `2026-10-13-monotone-catalog-ranges.md` (removed in block 10) and corrects stage 4's
D4, D5, D6 and D8. Five blocks, one stack cut from `main` at `ba32bc0`: #193 (10,
`feat/source-observations`), #194 (20, `feat/webui-source-interval`), #196 (30, `feat/sources-interval`),
block 40 (`docs/append-only-sources`), then the closing block 50 (`docs/source-points-closing`).

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
displaying node's gap). The closing block adds any the holistic review finds missing.

## Wrap counts

Draft, for block 50 to recount with `gh run list --branch <b> --workflow pr.yml --json
headSha,event,conclusion,createdAt` on each stack branch.

- **Fix-backs**: 0 so far.
- **Cascaded rebases**: 0 so far.
- **Runs**: one per branch for #193 (`3fb679b`), #194 (`4ea3b38`) and #196 (`97423d8`), all green;
  block 40's own run in its report.
- **Bodies the operator called unreadable**: none so far.

## Holistic review

To run at the head of Wrap over `git diff origin/main...origin/docs/append-only-sources`; its findings
and their exits go here.

## Pitfalls

- **A node whose `crawler.yml` still holds `decision_poll_interval_seconds` refuses to boot.** The
  release notes must say to delete the line; `docs/migration-4x.md` step 3 does.
- **The sources step's gate compares wall-clock times**: a clock stepped back suspends source reads until
  it passes the last start plus the interval again. Not handled; D3 names no monotonic clock.
- **With strict `<` before `read_at`, a point at the same instant never carries its own role**: that
  is what makes the same read written twice idempotent.
- **The file page shows the latest sighting's name in its eD2k link whatever the interval**: a
  timeline assertion must target `<td>name</td>`.
- **Literal template text is not escaped** (`interval's`), while interpolated text is.
- **The name page's period table holds hashless periods only.**
- **`uv run poe docs-build` fails on a dead anchor** (`Aborted because --strict flag is set`), checked
  again in block 40 with a broken link to `settings.md`'s new section.

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
- **The integration suites** were not run locally by block 30 (`compose_integration` reads the smoke
  config); CI runs them.
- Stage 4's carried-over items: a source read against a real amuled, the step's cost inside the cycle,
  a notification on a real apprise target.

## Next

The operator reviews the stack, the lead rebases it onto `main`, and the operator merges. **The lot
changes the image, but the next release waits for section 9's lot**: the node's next upgrade runs stage
1's 0006 to 0009 over its 5.9 GB catalog, and a copy before a migration that rewrites rows is required
first. At Wrap, `BACKLOG.md` loses "Search observations as time ranges", "Merge diverged copies of one
node's catalog" and "Paginate the file detail timeline", and gains the copy before a migration, the
webui in the visitor's time zone, and `backoff` under the search config. Once the node runs this lot,
the measures above.

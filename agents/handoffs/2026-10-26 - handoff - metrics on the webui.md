# Handoff: the node metrics served by the webui on 8080

Drafted by block 80 from the lot's block reports (#491, #492, #494 to #498) and its own, corrected by the closing
block 90 with the holistic review (`.reviews/metrics-on-the-webui-holistic.md`) and with blocks 20 and 85 as the
operator's review of #492 left them.

## State

Tier Spec lot. Spec `agents/specs/2026-10-25-metrics-on-the-webui.md` (approved by the operator 2026-10-26, after the
reviews `metrics-spec-review` and `metrics-spec-review-2`). It ships the backlog entry "The metrics served by the webui
on 8080", which block 90 deletes from `BACKLOG.md`.

One stack cut from `main` at `8229a42e`, which had not moved when block 90 was written (`git fetch`, 2026-10-26). Ten blocks with the closing
one: the spec's nine, and block 85 inserted after the operator's review of #492 (below). No split, no exemption.

The operator's review of #492 changed block 20: the module's dict of metadata and the single enum gave way to two
enums, `NodeCounter` and `NodeGauge`, each member declaring its exposed name, description and label names in its own
definition (commit `7f4fb5ab`), and blocks 40 to 80 were rebased over it. The review also asked why labels with known
values (`client`, `tier`, `network`, `kind`) are bare strings: typed labels came in the new block 85 (`ee08abfb`),
split from block 20 once both together reached 576 lines.

| Block | Pull request | Branch |
|---|---|---|
| 10 | #491 | `refactor/node-metric-names` |
| 20 | #492 | `refactor/node-metric-catalog` |
| 30 | #494 | `feat/webui-always-served` |
| 40 | #495 | `feat/node-metrics-on-the-webui` |
| 50 | #496 | `test/node-metric-store-contract` |
| 60 | #497 | `test/node-metrics-against-the-old-output` |
| 70 | #498 | `feat/drop-prometheus-client` |
| 80 | #499 | `docs/node-metrics-documents` |
| 85 | not opened at writing | `refactor/node-metric-labels` |
| 90 | the closing block's | `docs/metrics-on-the-webui-closing` |

Not merged at writing. The lot changes what the core image ships (`prometheus-client` leaves, `/metrics` moves to
8080, two `crawler.yml` keys refused): a v5 change, whose release waits for the two backlog entries that gate it
("A copy before a migration that rewrites rows", "The Grype scan back on p2pwatch at the v5 release").

## What was built

- **The word** (block 10, D9, C1): a metric's name took `node` (block 20 then split it into two enums),
  `ObservabilityPlan.metrics` became `node_metrics`; `AGENTS.md`'s glossary gained `node metric`, its types added by
  block 80.
- **The catalog in the domain** (block 20, D5, D6, as the operator's review changed it):
  `domain/observability/node_metric.py` holds the enums `NodeCounter` and `NodeGauge` (over a base `NodeMetric`), each
  member declaring its exposed name, description and label names; `CounterIncrement(counter, labels, amount)` takes a
  `NodeCounter` and `GaugeSetting(gauge, labels, value)` a `NodeGauge`, so mypy refuses an increment of a gauge. The
  structural guardrail moved to `test_policy`: every instruction `plan_observability` writes is built.
- **The typed labels** (block 85, D6 as the operator's review changed it): an instruction's labels are a frozen domain
  value, `ChannelLabels(client_name, channel)`, `ClientLabels(client_name)`, `DecisionLabels(tier)` or
  `SourceAlertLabels(network, kind)`, or `None` for an unlabelled metric; each member declares its `label_class`, and
  labels of another class raise `ValueError` at construction, since mypy cannot tie a member to its class. Each class
  writes its `(name, text)` pairs (`label_pairs()` on an instruction), on which the store and its fake key a series, so
  `NodeMetricSample(node_metric, labels, value)` and the exposition did not change.
- **The webui always served** (block 30, D13, D15): the `if` gating `_start_webui` gone, `WebuiConfig.enabled` and its
  default gone; `_REMOVED_KEYS` reads dotted paths (`_holds_key_path`), so `webui.enabled` is refused by its path.
- **The new path** (block 40, D1 to D4, D7, D8, D12): the pair `NodeMetricWriter` (`record_increment`, `set_gauge`) and
  `NodeMetricReader` (`read_samples`), implemented by `InMemoryNodeMetricStore`
  (`adapters/driven/in_memory_node_metric_store.py`), which swaps an immutable snapshot on each write (single writer:
  the crawler's loop); the use case `ListNodeMetrics` behind `NodeMetricLister`, returning `NodeMetricListing`
  (`samples_by_node_metric`, in the catalog's order); the webui's `prometheus_text` module and the `/metrics` route,
  served as `text/plain; version=0.0.4; charset=utf-8` whatever the `Accept` header. The dispatcher wrote both the old
  recorder and the new store until block 70.
- **The contract** (block 50, D10): `NodeMetricStoreContract`, run by `TestInMemoryNodeMetricStore` and
  `TestFakeNodeMetricStore`; the step tests read the node metrics through the Reader of `FakeNodeMetricStore`; the
  webui tests list them through `FakeNodeMetricLister`.
- **The old output kept as a fixture** (block 60, D11): `C/tests/fixtures/old_prometheus_text_unwritten.txt` and
  `old_prometheus_text_written.txt`, captured from `PrometheusMetricsRecorder` with prometheus-client 0.26.0
  (`_created` lines stripped); the comparison test compares the `# HELP` / `# TYPE` lines and the samples as sets. The
  full-mode wiring test and the compose smoke read `/metrics` on 8080.
- **The old path removed** (block 70, D14, D15, What goes away): `MetricsRecorder`, `PrometheusMetricsRecorder`,
  `start_metrics_server`, `MetricsConfig`, the doubles `FakeMetricsRecorder` and `FakeMetricsServer`, `_bool` (its last
  caller gone), `prometheus-client` from `pyproject.toml`, `uv.lock` and the image; `observability.metrics` refused by
  its path; the smoke checks nothing listens on 9090 in the core container.
- **The holistic review's fixes** (block 90): uvicorn's access log leaves out the `/metrics` requests, a
  `CounterIncrement` of a negative amount is refused, the contract compares one sample per series, the step tests
  compare the samples as sets; below.
- **The documents** (block 80): `docs/migration-4x.md` (both refusals in step 3, two bullets under "Ce qui change":
  the scrape on 8080 and the format, the webui always served), `docs/settings.md` ("Métriques Prometheus" rewritten),
  `docs/operate.md` (the `/metrics` route and the 8080 warning), `docs/legal.md` (its two mentions),
  `docs/contributing/architecture.md` (both diagrams, the hexagon table, section 10), `AGENTS.md` (the WebUI and
  Observability rows, Boundary discipline, the glossary).

## Acceptance

1. Block 60: the wiring test, with the composition handing `ListNodeMetrics` a fresh store, failed with
   `assert 'p2pwatch_crawler_up 1.0' in [...]`.
2. Block 40: `test_prometheus_text.py`, each case line by line.
3. Block 60: one sample of the written fixture edited (2.0 to 3.0) fails the comparison with `Extra items in the left
   set`; the escaped newline edited fails it too.
4. Block 50: the contract run by both subclasses; `test_contract_subclasses.py` and `test_port_files.py` pass with no
   new exemption. Block 90: the snapshot test deleted (the spec's acceptance 4 marked `Corrected`); the multiset
   comparison fails on `InMemoryNodeMetricStore` made to return its samples twice
   (`assert Counter({Node...alue=1.0): 2}) == Counter({Node...alue=1.0): 1})`).
5. Block 20: the domain's unit tests; the moved guardrail, the policy's label order swapped by hand, failed with
   `ValueError: p2pwatch_searches takes the labels ('client', 'channel'), not ('channel', 'client')`. Block 90, over
   block 85's labels: the policy writing `ChannelLabels` for `CLIENT_UNREACHABLE` fails
   `test_plan_observability_maps_every_event` with `ValueError: p2pwatch_client_unreachable takes ClientLabels, given
   ChannelLabels` once the duplicate left; each refusal shown failing against an implementation that lacks it
   (finding 6 below); the negative amount `DID NOT RAISE ValueError` before its check.
6. Block 40: `test_list_node_metrics.py`.
7. Blocks 30 and 70: `test_a_removed_key_of_a_section_is_refused_by_its_path`, `DID NOT RAISE InvalidConfigError`
   before each key joined `_REMOVED_KEYS`.
8. Block 70: the `git grep` prints nothing, `grep -c prometheus uv.lock` prints 0, a core image built from the branch
   gives `ModuleNotFoundError: No module named 'prometheus_client'`; the smoke passed locally with the 9090 probe, the
   probe's logic checked both ways against a listener on the host.
9. Block 80: the `git grep` prints four lines, all in `docs/migration-4x.md`, each naming what was removed (lines 44,
   45, 141, 142).
10. Every block's report: `uv run poe check` exit 0 at its tip; `uv run poe docs-build` "No issues found" where run.

## The holistic review's findings

`metrics-holistic-review` over blocks 10 to 80 as they stood before the operator's review of #492: CRITICAL 0, MAJOR 1,
MINOR 9. Every finding exits fixed in the lot: nine in block 90, carried onto blocks 20 and 85's types when block 90
was rebased over them (6 with block 20's rewrite), and one by block 20's rewrite alone (9).

1. **MAJOR, uvicorn's access log wrote a line per scrape** (240 an hour at Prometheus's default interval, where the
   9090 server wrote none). Fixed, the operator's option A: `_MetricsScrapeFilter`, a `logging.Filter` on
   `uvicorn.access`, set through the `log_config` that `UvicornServerThread` hands uvicorn (uvicorn's own
   `LOGGING_CONFIG`, copied). `test_the_access_log_leaves_out_the_metrics_scrapes`, watched failing first:
   `At index 0 diff: '"GET /metrics HTTP/1.1" 200' != '"GET / HTTP/1.1" 200'`.
2. **`FakeNodeMetricStore`'s first-write order, relied on by three step tests.** Fixed: the search worker's test
   compares all four samples as a set (the fourth, `DECISIONS{tier="download"}`, was hidden by a `[:3]` slice), the
   two dispatcher tests with two samples compare sets, and the fake's docstring no longer promises an order. The fake
   made to read its series in reverse passes the new tests and fails the three old ones. `SearchExecuted` dispatched
   first stays checked by the search worker's `logger.lines`.
3. **A negative counter increment was accepted**, which `prometheus_client` refused and Prometheus reads as a reset.
   Fixed: `CounterIncrement` raises `ValueError` (`p2pwatch_searches takes an amount of 0 or more, not -1.0`),
   `test_an_increment_of_a_negative_amount_cannot_be_built` watched failing first (`DID NOT RAISE ValueError`).
4. **The contract's set comparison let a store return a series twice.** Fixed: a multiset (`collections.Counter`).
5. **Two contract tests could not fail** (a later write leaving a read tuple unchanged; a read from another thread).
   Fixed: both deleted, the spec's acceptance 4 marked `Corrected`.
6. **Block 20's TDD evidence was thin.** Fixed by block 20's rewrite and by mutations run in block 90 over the whole
   crawler suite, on the current types. The kind is now the enum: mypy refuses `CounterIncrement(NodeGauge.CRAWLER_UP)`
   (`Argument 1 to "CounterIncrement" has incompatible type "NodeGauge"; expected "NodeCounter"`) and the `GaugeSetting`
   of a counter likewise. The label class check removed fails the three cases of
   `test_an_increment_whose_labels_are_not_its_counters_cannot_be_built` and
   `test_a_setting_whose_labels_are_not_its_gauges_cannot_be_built`, 4 failed. The positive tests pass against any
   dataclass, as the review says: they state what an instruction holds, and the refusals carry the checks.
7. **`test_every_node_metric_the_policy_writes_fits_its_catalog` duplicated the mapping test.** Fixed: deleted, one
   comment above `test_plan_observability_maps_every_event` keeps its point.
8. **`AGENTS.md`'s WebUI row sent every route through a display.** Fixed: the text routes (`/metrics`, written by
   `prometheus_text.py`, and `/console.csv`) are named aside.
9. **The `# TYPE` word was the domain enum's value.** Fixed by block 20's rewrite: `NodeMetricKind` is gone, and
   `prometheus_text` writes `counter` or `gauge` from the member's enum, so block 90's own `match` on the kind was
   dropped when it was rebased.
10. **Two long lines**, `docs/legal.md:99` and `docs/operate.md:285`. Fixed: rewrapped.

## Departures from the spec

Each is marked `(Corrected: ...)` in the spec.

- Block 20: the catalog in a new module `domain/observability/node_metric.py`, not `policy.py`; D5's one enum with a
  kind became two enums, `NodeCounter` and `NodeGauge`, after the operator's review (the kind is the type, checked by
  mypy, where D6 had a `ValueError`); a member's value is a private frozen `_Declaration`, since an enum `__new__` runs
  only at import, which `_unit-coverage-check` credits to no test; `CounterIncrement | GaugeSetting` written inline,
  no union alias.
- Block 85: the labels a class per shape, checked at construction by `ValueError`, where D6 checked label names; each
  class's `names` fixes the order of its pairs, so a series' label tuple stays canonical for the store.
- Block 30: D15's "new check of nested keys" is `_REMOVED_KEYS` reading dotted paths, not a second check.
- Block 40: `NodeMetricSample` in the domain module, not in the Reader's port file (a driven read port returns domain
  types only, and the driving port's `NodeMetricListing` holds samples); `NodeMetricListing` is
  `samples_by_node_metric`, the description read from each member; sample values written with
  Python's `repr` (`500000000000.0`) where the library wrote Go's short form, equal as floats.
- Block 50: two corrections of block 40 joined it, decided by the lead (the tests that used `InMemoryNodeMetricStore`
  as a double use `FakeNodeMetricStore`; the webui tests use `FakeNodeMetricLister`).
- Block 60: two fixtures, not one (the fresh registry checks D7 too); the sequence a literal tuple in the test module,
  not `plan_observability` over `test_policy`'s cases, so a later policy change cannot break a fixture that can no
  longer be recaptured; the real chain compared, not doubles; the metadata lines compared as a set.
- Block 70: the 9090 probe could not have failed against block 60's image (the smoke's `crawler.yml` never set
  `observability.metrics`): it guards a server coming back. The fixture comparison test renamed
  `test_the_text_holds_the_metadata_and_samples_the_4x_recorder_wrote`, so acceptance 8's grep finds nothing.
- Block 90: the access log filter is set through uvicorn's `log_config` (a copy of its `LOGGING_CONFIG` whose
  `uvicorn.access` logger holds the filter), not by `logging.getLogger("uvicorn.access").addFilter`, which
  `code-pattern-check`'s rule on literal logger names refuses and which would stack a filter per server built.
- Block 80: the glossary's `node metric` gains its types (C1 had them land with the blocks that added them, which none
  did); `docs/operate.md` gains a `/metrics` row in its routes table and names it in the 8080 warning; `docs/settings.md`
  says what an operator sees when the webui falls (D16).

## Class 1 fixes

None in any block.

## Class 2 questions

None in any block.

## Pitfalls

- **A test compares a reader's samples as a set (a multiset in the contract), never in order**: `NodeMetricReader`
  promises no order, and `FakeNodeMetricStore`'s dict order is no promise either; what was dispatched first is read
  from the logger's lines (block 90, from three step tests that leaned on the fake's order).
- **uvicorn's access logger does not propagate**: `caplog` sees its records only through its handler added to
  `uvicorn.access`, after the `uvicorn.Config` is built, since its `dictConfig` drops that logger's handlers (block 90).
- **A mutation that keeps a file's size, written within the second of the previous version, can run the stale
  `.pyc`**: the gate then fails, or passes, on code no longer there (39 failures in block 20, two wrong mutation
  results in block 90). Run mutations with `PYTHONDONTWRITEBYTECODE=1`, or delete the `__pycache__` entries.
- **A `match` on `GaugeSetting(value=float(v))` does not match an `int` value at runtime**, and leaves a branch no test
  takes: route with `isinstance` and `value is None` (block 20).
- **Starlette appends `; charset=utf-8` to a `text/*` media type that lacks one**: the constant spells the full 0.0.4
  content type (block 40).
- **prometheus-client 0.26.0 writes a sample's labels alphabetically**, families counters first; the webui's writer
  keeps the catalog's order, hence the comparison by sets (block 60).
- **Removing a config key can orphan its parser's helper**: `_bool` lost its last caller with `observability.metrics`
  (block 70).

## Not validated

- The operator's own Prometheus, if any scrapes the deployed node: its target moves from 9090 to 8080 at the v5
  upgrade.
- Whether Prometheus stores the OpenMetrics `_created` lines it reads today as series (the spec's "Not validated"):
  gone either way in v5, which the migration says.
- Locally, the integration suites ran only where a report says so (the smoke in blocks 60 and 70, under Docker
  Desktop); CI's `validate / gate` runs them all, on both architectures. Block 90 ran none locally (it changes no
  wiring): its CI run checks them, after the push that follows the rebase over block 85.

## Wrap counts

- 1 fix-back: block 20, from the operator's review of #492, which split into block 20 and the new block 85.
- 1 cascaded rebase, over the new block 20: its conflicts resolved by the teammates of blocks 40, 50, 70, 80 and 90;
  block 60 rebased cleanly but still used the old names, and was fixed after.
- The runs it re-triggers: those of the push that follows, one per branch.
- No body called unreadable.
- Block 90 measured 113 changed lines, 13 files, against block 85.

Before the review, `gh run list --branch <branch> --workflow PR` showed one successful run per branch for blocks 10
to 80, and block 90's first run (#500) passed.

## Next

- The operator reads the stack; the lead rebases it onto the current `main`; the operator merges it.
- Then the backlog, "A copy before a migration that rewrites rows" first: it gates the v5 release this lot ships in.

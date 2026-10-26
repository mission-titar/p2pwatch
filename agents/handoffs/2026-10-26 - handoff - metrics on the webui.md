# Handoff: the node metrics served by the webui on 8080

Drafted by block 80 from the lot's block reports (#491, #492, #494 to #498) and its own, for the closing block 90 to
correct with the holistic review.

## State

Tier Spec lot. Spec `agents/specs/2026-10-25-metrics-on-the-webui.md` (approved by the operator 2026-10-26, after the
reviews `metrics-spec-review` and `metrics-spec-review-2`). It ships the backlog entry "The metrics served by the webui
on 8080", which block 90 deletes from `BACKLOG.md`.

One stack cut from `main` at `8229a42e`, which had not moved when block 80 was written. Ten blocks with the closing
one: the spec's nine, and block 85 inserted after the operator's review of #492 (below). No split, no exemption.

The operator's review of #492 changed block 20: the module's dict of metadata and the single enum gave way to two
enums, `NodeCounter` and `NodeGauge`, each member declaring its exposed name, description and label names in its own
definition (commit `7f4fb5ab`), and blocks 40 to 80 were rebased over it. The review also asked why labels with known
values (`client`, `tier`, `network`, `kind`) are bare strings: typed labels come in the new block 85.

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
| 85 | not cut at writing | typed labels |
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
  `NodeCounter` and `GaugeSetting(gauge, labels, value)` a `NodeGauge`, so mypy refuses an increment of a gauge, and
  each raises `ValueError` at construction when its labels are not exactly the metric's, in the catalog's order. The
  structural guardrail moved to `test_policy`: every instruction `plan_observability` writes is built.
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
   new exemption.
5. Block 20: the domain's unit tests; the moved guardrail, the policy's label order swapped by hand, failed with
   `ValueError: p2pwatch_searches takes the labels ('client', 'channel'), not ('channel', 'client')`.
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

For block 90 to fill.

## Departures from the spec

- Block 20: the catalog in a new module `domain/observability/node_metric.py`, not `policy.py`; D5's one enum with a
  kind became two enums, `NodeCounter` and `NodeGauge`, after the operator's review (the kind is the type, checked by
  mypy, where D6 had a `ValueError`); labels "exactly the metric's" read strictly, names in the
  catalog's order, which makes a series' label tuple canonical for the store; `CounterIncrement | GaugeSetting` written
  inline, no union alias.
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
- Block 80: the glossary's `node metric` gains its types (C1 had them land with the blocks that added them, which none
  did); `docs/operate.md` gains a `/metrics` row in its routes table and names it in the 8080 warning; `docs/settings.md`
  says what an operator sees when the webui falls (D16).

## Class 1 fixes

None in any block.

## Class 2 questions

None in any block.

## Pitfalls

- **`FakeNodeMetricStore` returns its series in first-write order, which `NodeMetricReader` does not promise**, and
  the search worker's test relies on it to check that `SearchExecuted`'s counters come before the observation's
  (block 50). The lead's open point, for the holistic review to judge.
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
  Desktop); CI's `validate / gate` runs them all, on both architectures. Block 70's run was in progress, and block 80's
  not started, when this was drafted.

## Wrap counts

From `gh run list --branch <branch> --workflow PR`, 2026-10-26, before the operator's review: one run per branch for
blocks 10 to 60, all successful; block 70's one run in progress. The review of #492 then brought one fix-back (block
20) and a cascaded rebase of blocks 30 to 80, whose re-triggered runs block 90 counts. No body called unreadable.

## Next

- Block 85: typed labels, asked by the operator's review of #492.
- Block 90: the holistic review's findings, `BACKLOG.md` (the entry deleted), this handoff corrected.
- The operator reads the stack; the lead rebases it onto the current `main`; the operator merges it.
- Then the backlog, "A copy before a migration that rewrites rows" first: it gates the v5 release this lot ships in.

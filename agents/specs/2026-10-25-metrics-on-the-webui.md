# The node metrics served by the webui on 8080

- Date: 2026-10-25. Status: approved by the operator, 2026-10-26, after two reviews (`metrics-spec-review`, `metrics-spec-review-2`).
- Tier: Spec. Origin: the backlog entry "The metrics served by the webui on 8080", the Discuss of 2026-10-25.
- Size: 9 blocks with the closing one; blocks 40 and 70 sit close to a bound.
- Measured on `main` at `8229a42e`. `C` is `packages/crawler/`.

## In short

- `/metrics` becomes a webui route on 8080, like every other page: one call to a use case through its driving port,
  which reads the node metrics from an in-memory store through its `Reader`. Prometheus's own HTTP server on 9090 goes
  away.
- The node metrics are a store of our own state: the observability dispatcher writes each counter increment and gauge
  setting through a `NodeMetricWriter`, the webui reads the samples through a `NodeMetricReader`, and
  `prometheus_client` leaves the image. The webui writes the Prometheus text format itself.
- `metric` becomes `node metric` in every layer, so a metric is never mistaken for a file's or a source's figures. The
  domain's catalog of node metrics (kind, description, label names) refuses an instruction that does not fit it.
- `webui.enabled` and `observability.metrics` (`enabled`, `port`) are removed from `crawler.yml`, and refused when
  present. A breaking change for v5, written into `docs/migration-4x.md`.

## What an operator sees change

- Prometheus scrapes `http://<node>:8080/metrics`. There is no 9090 port to publish any more.
- The exposition format changes. Today `prometheus_client` answers Prometheus's default `Accept` header (2.x and 3.x)
  with OpenMetrics 1.0.0; v5 serves the text format 0.0.4, which every Prometheus accepts. The series keep their names,
  labels and values; the counters' `_created` samples go, and a counter's metadata family takes its `_total` suffix
  (`p2pwatch_searches_total`, where OpenMetrics names it `p2pwatch_searches`).
- A `crawler.yml` that still sets `webui.enabled` or `observability.metrics` is refused at start, naming the key.
- The webui always listens on 8080. Removing the `"8080:8080"` line from `ports:` in `compose.yml` takes it off the
  host's network; the compose network still reaches it (the smoke checks the webui's `/health` from `ed2k`).
- Behind a reverse proxy, `/metrics` is reachable wherever 8080 is, without authentication, unless the proxy filters it.
- If the webui's thread crashes (it degrades, the crawl goes on: decision 1 of §17,
  `agents/specs/2026-07-06-monolith-consolidation.md`), `/metrics` stops answering with it.

## Conventions

- **C1. Glossary: `node metric`**: a measurement of the node's own running (searches done, free disk, the crawler up),
  which Prometheus reads; never a file's or a source's figures. Its types: `NodeCounter` and `NodeGauge` (each member
  with its exposed name, description and label names) (Corrected: the operator's review of block 20, PR #492: was
  `NodeMetricName` with its kind), `CounterIncrement` and `GaugeSetting` (what the policy writes), `NodeMetricSample`
  (one series and its current value). Naming, block 10 for the word, the types with the blocks that add them.
  (Corrected: the glossary gained the word in block 10 and every type in block 80, since no earlier block added them.)

## Decisions

- **D1. One HTTP server.** `/metrics` is a route of the server that already serves the webui on 8080. Why: one port to
  publish, proxy and document, and one server thread less to start and stop. (Corrected: uvicorn's access log leaves
  out the `/metrics` requests, by a `logging.Filter` on `uvicorn.access` the webui adapter installs, since every
  scrape wrote a line where the 9090 server wrote none; block 90, from the holistic review.)
- **D2. `/metrics` is a webui route like the others.** `handle_metrics` makes one call to `NodeMetricLister`, the
  driving port of the use case `ListNodeMetrics`, and renders its `NodeMetricListing`. Why: Prometheus is an actor
  that calls the node, as the browser is (Cockburn's driving side); every page goes through a use case behind a driving
  port, and the scrape is no exception.
- **D3. The node metrics are our own state, held by a store.** The driven port `MetricsRecorder` gives way to the pair
  `NodeMetricWriter` (`record_increment(increment)`, `set_gauge(setting)`) and `NodeMetricReader`
  (`read_samples() -> tuple[NodeMetricSample, ...]`), implemented by `InMemoryNodeMetricStore`. Why: `AGENTS.md`'s
  Naming makes a port over our own state a `Writer` and `Reader` pair implemented by one adapter; an increment is a
  fact added (`record_`), a gauge setting replaces a current value (`set_`), so each verb says what it does (operator's
  choice over amending the rule for a single `record_instruction`).
- **D4. The store swaps an immutable snapshot on each write.** The crawler's loop is the only writer (every
  `dispatch` in `C/src` is awaited on it), the webui's thread reads; a read takes the current snapshot whole. The
  single-writer premise goes into `InMemoryNodeMetricStore`'s docstring. Why: the pattern `InMemoryStatusReadingStore`
  already follows for the same two threads, with no lock.
- **D5. The catalog of node metrics moves to the domain.** Each `NodeMetricName` carries its kind (`NodeMetricKind`,
  counter or gauge), its description and its label names, which `PrometheusMetricsRecorder`'s `_COUNTERS` and `_GAUGES`
  hold today. Why: what a metric means is domain knowledge; the use case needs the label names to tell an unlabelled
  metric never written (one sample at 0) from a labelled one (no sample), and the instructions need them to be checked
  (D6). (Corrected: the operator's review of block 20, PR #492: `NodeMetricName`, `NodeMetricKind` and a module dict of
  metadata gave way to two enums, `NodeCounter` and `NodeGauge`, over a memberless `NodeMetric`; each member declares in
  its own definition its exposed name, description and label names, its value a private frozen declaration of the three,
  since an enum `__new__` making the name the value runs only at import, which `_unit-coverage-check` credits to no
  test.) (Corrected: the catalog lives in a module of its own, `domain/observability/node_metric.py`, with
  `NodeMetricSample` and the label classes.)
- **D6. `MetricInstruction` splits into `CounterIncrement` and `GaugeSetting`, each refusing at construction what does
  not fit its catalog entry.** `CounterIncrement(name, labels, amount)` names a counter; `GaugeSetting(name, labels,
  value)` names a gauge, its `value` `None` to remove the series. A name of the other kind, or labels whose names are
  not exactly the metric's, raises `ValueError`. `MetricOperation` goes. Why: today `prometheus_client` raises on a
  wrong or missing label and on an `inc` to a gauge, and `test_every_emitted_metric_is_declared_in_the_metrics_recorder`
  rests on it; an in-memory store would take any instruction silently. The type makes a wrong instruction unbuildable,
  and the structural test is kept, over `plan_observability`'s cases, against the construction. (Corrected: the
  operator's review of block 20, PR #492: `CounterIncrement(counter, labels, amount)` takes a `NodeCounter` and
  `GaugeSetting(gauge, labels, value)` a `NodeGauge`, so mypy refuses an increment of a gauge; the labels stay names
  checked against the member's here, and become typed label classes in block 85.) (Corrected: block 85, from the same
  review: the labels are typed, a frozen domain dataclass per shape, `ChannelLabels(client_name, channel)`,
  `ClientLabels(client_name)`, `DecisionLabels(tier)` (a `DecisionTier` or `"retracted"`) and
  `SourceAlertLabels(network, kind)`, `None` for an unlabelled metric; labels that are not an instance of the member's
  label class raise `ValueError`, since mypy cannot tie a member to its class. Each class writes its `(name, text)`
  pairs, on which the store keys a series, so `NodeMetricSample` and the exposition do not change.) (Corrected: a
  negative `amount` raises too, as `prometheus_client` refused one, added in block 90; the structural test is
  `test_plan_observability_maps_every_event`, which builds every instruction already, its separate copy deleted in
  block 90.)
- **D7. The listing names every metric of the catalog.** `NodeMetricListing` holds each `NodeCounter` and `NodeGauge`
  (Corrected: was `NodeMetricName`, D5) with its kind, description and samples; a metric without labels that nothing has
  written has one sample at 0. An increment of 0 creates its series at 0; removing an absent series does nothing. Why:
  the series stay those `prometheus_client` exposes today (probed on 0.26.0 by the second review). (Corrected:
  `NodeMetricListing` is `samples_by_node_metric`, in the catalog's order, the description read from each member.)
- **D8. The webui writes the Prometheus text format 0.0.4 itself**, in a module of the webui beside `format.py`: per
  metric `# HELP` and `# TYPE`, then a line per sample, label values escaped (`\\`, `"`, newline), served as
  `text/plain; version=0.0.4; charset=utf-8` whatever the `Accept` header. A counter's name takes `_total` on its
  `# HELP`, `# TYPE` and sample lines, as `prometheus_client` writes 0.0.4 today. Like `/console.csv`, the text goes
  through no `<Thing>Display`. `prometheus-client` leaves `C/pyproject.toml`. Why: the format is the adapter's, as the
  Markdown is `AppriseNotifier`'s; a short text format needs no library built to own its registry, and the image loses
  a dependency (operator's choice). 0.0.4 over OpenMetrics: Prometheus's default `scrape_protocols` accept it, and
  OpenMetrics' `_created` and `# EOF` rules buy nothing here. (Corrected: a sample's value is written with Python's
  `repr` (`500000000000.0`) where the library wrote Go's short form, the same float; the `# TYPE` word is the
  adapter's, chosen by the member's enum, `NodeCounter` or `NodeGauge`, since block 20.)
- **D9. `metric` becomes `node metric` in every layer.** `MetricName` becomes `NodeMetricName`,
  `ObservabilityPlan.metrics` becomes `node_metrics`, the dispatcher's `metrics_recorder` becomes `node_metric_writer`
  when its port changes. Why: the domain handles many figures (file sizes, received bytes, coverage counts), and a bare
  `metric` does not say whose (operator's choice). (Corrected: block 20 then replaced `NodeMetricName` by `NodeCounter`
  and `NodeGauge`, D5.)
- **D10. The step tests read the node metrics through the Reader.** `FakeMetricsRecorder`, a spy that keeps the
  instructions, gives way to `FakeNodeMetricStore`, a fake that the pair's contract `NodeMetricStoreContract` runs, as
  it runs `InMemoryNodeMetricStore`. Why: the contract tests' rules make a Writer and Reader pair's double a working
  store, and the port is the reference: a test asserts what a reader sees, not the calls a writer received.
- **D11. The new output is checked against the old.** Block 60, while `prometheus_client` is still in the tree,
  captures a fixture: the text 0.0.4 that `PrometheusMetricsRecorder` writes for a fixed sequence of instructions
  covering every case of `test_policy`, `_created` lines stripped. A test asserts that the webui's writer over the same
  sequence gives the same `# HELP` and `# TYPE` lines and the same samples, compared as sets of (name, labels, value).
  The fixture stays once the library leaves. (Corrected: two fixtures, a fresh registry's output checking D7 too; the
  sequence a literal tuple in the test module, so a later change of the policy cannot break a fixture no one can
  recapture; the metadata lines compared as a set, since the library orders families counters first.) Why: D7's promise is what keeps an operator's dashboards and alerts
  working, and a test whose expected text the implementer writes cannot fail it.
- **D12. The cut keeps every block green alone.** vulture fails a block whose new `src` has no production caller, and
  `test_port_files.py` refuses a Writer without its Reader, so the store, its use case and the route land together in
  block 40. To reach them without removing `prometheus_client` in the same block, the dispatcher writes both the old
  recorder and the new store from block 40 to block 70, the stack merging as one so no release carries it. Why: a
  temporary collector feeding 9090 from the store, the other way, would have a driving surface read a driven port,
  the departure this lot removes.
- **D13. `webui.enabled` is removed.** Why: with the metrics on the webui's server, switching the webui off would
  silently switch the metrics off too. The change it brings is accepted: no setting stops the node from listening on
  8080 inside the compose network, where today `webui.enabled: false` opens no listener at all.
- **D14. `observability.metrics` is removed, `enabled` and `port` with it.** Why: the port has nothing left to set, and
  an off switch for a read-only text page on a surface that is already unauthenticated protects nothing.
- **D15. Both are refused, not ignored, by a new check of nested keys.** A `crawler.yml` holding `webui.enabled` or
  `observability.metrics` raises `InvalidConfigError` whose `key` is that dotted path, worded as the existing removed
  keys ("was removed, delete it from crawler.yml"). `_REMOVED_KEYS` reads top-level keys only, so the nested ones need
  a check of their own. Why: an operator who set either one believes it applies; `_parse_webui` and
  `_parse_observability` ignore unknown keys silently today, which would hide exactly these two. (Corrected: no second
  check; `_REMOVED_KEYS` reads dotted paths, so both keys join it, with the same error and wording.)
- **D16. The webui's crash takes the metrics with it.** Accepted: Prometheus then records the target down (its own
  `up` series at 0), which is the signal an operator watches anyway.

## What goes away

`MetricsRecorder`, `PrometheusMetricsRecorder`, `MetricInstruction`, `MetricOperation`, `start_metrics_server`,
`_METRICS_SERVER_JOIN_TIMEOUT_SECONDS`, `MetricsConfig`, `ObservabilityConfig.metrics` and `.metrics_port`,
`WebuiConfig.enabled`, `DEFAULT_WEBUI_ENABLED`, the `if` that gates `_start_webui` in `CrawlerComposition`, and with
their tests the doubles `FakeMetricsRecorder` and `FakeMetricsServer`. (Corrected: `_bool` of `crawler_config.py`
too, whose last caller was `observability.metrics`.) The `_config()` helper of
`C/tests/composition/test_crawler_composition_wiring.py` stops passing `"webui": {"enabled": False}`: every composition
test then starts the webui, on `("127.0.0.1", 0)`.

## Documents

- `docs/migration-4x.md`: step 3 (editing `crawler.yml`) quotes both refusals word for word, as it quotes the others;
  a bullet under "Ce qui change" names the scrape target on 8080, the format change (D8), the `_created` samples gone
  and the webui always served.
- `docs/settings.md` ("Métriques Prometheus"): `/metrics` on 8080, the `scrape_config` example targeting `:8080`, the
  reverse-proxy warning; the paragraph on `observability.metrics.enabled` goes.
- `docs/operate.md`, `docs/troubleshooting-start.md`, `docs/legal.md` (its two `/metrics` mentions, checked),
  `docs/contributing/architecture.md` (its text, its diagrams, and line 156, which lists Prometheus among what the
  adapters drive, where it is now a driving actor): each mention of either key, of 9090, of `PrometheusMetricsRecorder`.
  (Corrected: `docs/operate.md` also gains a `/metrics` row in its routes table and names it in the 8080 warning;
  `docs/settings.md` and the migration say what an operator sees when the webui falls, D16.)
- `deploy/crawler.yml`, `tests/smoke/crawler.yml`, `C/tests/integration/test_crawler_loop.py`: the keys deleted.
- `AGENTS.md`: the WebUI row of "Where the code lives" names `/metrics` and drops "`crawler.yml`'s `webui.enabled`
  only gates the whole surface"; the Observability row names the store; Boundary discipline's example (a
  `PrometheusMetricsRecorder` failure) becomes the store's; the glossary gains `node metric` (C1).

## Acceptance

1. **The composition serves `/metrics` on the webui's address.** The rewritten
   `test_full_mode_catalogues_queues_serves_the_webui_and_metrics_and_stops_on_restart`
   (`C/tests/composition/test_crawler_composition_wiring.py`) gets `http://<webui host>:<webui port>/metrics` without
   following redirects: status 200, content type `text/plain; version=0.0.4; charset=utf-8`, the body holding a
   `p2pwatch_crawler_up` sample at 1 and a `p2pwatch_observations_total{` line. Fails today: 404 from the webui.
2. **The writer renders the listing.** Unit tests of the webui module that writes the format: a counter with labels, a
   gauge without, a label value holding `"`, `\` and a newline, and a metric with no sample, each against its expected
   text, line by line.
3. **The new output is the old one** (D11): the comparison test against the captured fixture passes, and fails when
   one sample of the fixture is edited.
4. **The store keeps its promise.** `NodeMetricStoreContract` states the ports' docstrings: an increment adds to its
   series, an increment of 0 creates it at 0, a setting replaces its series, a setting of `None` drops it and does
   nothing on an absent one, series apart by labels, a tuple `read_samples` returned is unchanged by a later write; run
   by `TestInMemoryNodeMetricStore` and `TestFakeNodeMetricStore`. (Corrected: the snapshot test is deleted, since the
   return type, a tuple of frozen dataclasses, already guarantees it and no implementation could fail it; the series
   apart by labels are compared as a multiset, so a store returning a series twice fails; block 90.) `test_contract_subclasses.py` and
   `test_port_files.py` pass with no new exemption.
5. **A wrong instruction cannot be built.** Unit tests of the domain: missing labels, an extra label and labels on an
   unlabelled metric each raise `ValueError` (Corrected: a counter named for a gauge is mypy's to refuse, D6). The
   structural test builds every instruction `plan_observability` writes over `test_policy`'s cases. (Corrected: a
   `CounterIncrement` of a negative amount raises too, since block 90; the structural test is the mapping test,
   `test_plan_observability_maps_every_event`.)
6. **The use case lists the whole catalog.** Unit tests of `ListNodeMetrics`: every `NodeCounter` and `NodeGauge`
   (Corrected: was `NodeMetricName`, D5) appears once with its kind and description; an unlabelled metric never written
   has one sample at 0; a labelled one never written has none.
7. **Each removed key is refused by name.** Unit tests of `C/src/p2pwatch/domain/crawler_config.py`: `webui:
   {enabled: true}` raises `InvalidConfigError` whose `key` is `webui.enabled`; `observability: {metrics: {enabled:
   true, port: 9090}}` raises one whose `key` is `observability.metrics`; both messages say "was removed". Fails today:
   both parse. The YAML files are observed by the tests that load them: `test_filesystem_config_checker.py` and
   `test_validate_config.py` (`deploy/crawler.yml`), the compose smoke (`tests/smoke/crawler.yml`).
8. **No library, no second server.** `git grep -n -E "prometheus_client|prometheus-client|start_metrics_server" --
   packages` returns nothing; `uv.lock` no longer lists `prometheus-client`. The compose smoke gets
   `http://localhost:8080/metrics` from the core container (status 200, a `p2pwatch_crawler_up` sample) and its
   connection to `localhost:9090` is refused; the core still publishes only `8080/tcp`. Run by CI's `validate / gate`
   on both architectures.
9. **No stale mention.** `git grep -n -w -E
   "webui\.enabled|observability\.metrics|9090|MetricsRecorder|PrometheusMetricsRecorder|MetricName|MetricInstruction"
   -- docs AGENTS.md` returns only the `docs/migration-4x.md` lines that name what was removed.
10. `uv run poe check` and `uv run poe docs-build` pass at every block's tip.

## Not validated here

- The operator's own Prometheus, if any scrapes the deployed node: its target moves from 9090 to 8080 at the v5
  upgrade.
- Whether Prometheus stores the OpenMetrics `_created` lines it reads today as series: settled only by scraping
  today's 9090 with a stock `prom/prometheus` and querying `count({__name__=~"p2pwatch_.*_created"})`. Either way they
  are gone in v5, which the migration says.

## Adjacent backlog items

- "A copy before a migration that rewrites rows" and "The Grype scan back on p2pwatch at the v5 release": both gate
  the v5 release this change ships in, neither touches the metrics or the webui. They stay open.
- "The node page shows a node id set in `crawler.yml`", "Sort the files view by first seen" and "The webui in the
  visitor's time zone": webui work unrelated to how the webui is served. They stay open.
- "A generic way to write the tests' stubs and spies": D10 removes one spy, `FakeMetricsRecorder`, by turning it into a
  fake; the generic mechanism stays postponed.
- "`client_name` and `channel` typed across the domain" (Corrected: added by block 90, the operator agreeing, after
  block 85 typed the labels): `ChannelLabels` and `ClientLabels` still hold both as `str`, as the events and the
  search tasks do, though their values are known; typing them touches every layer, not the metrics alone.

## Blocks

Estimates by `metrics-estimate-2` on `main` at `8229a42e`, within 15 %, re-measured on this cut.

| # | Branch | Content | Estimate |
|---|--------|---------|----------|
| 10 | `refactor/node-metric-names` | D9's renames but the dispatcher's parameter, C1's word; mechanical | ~110 lines, 9 files |
| 20 | `refactor/node-metric-catalog` | D5, D6: `NodeMetricKind`, the catalog on `NodeMetricName`, `CounterIncrement` and `GaugeSetting` checked at construction, which `PrometheusMetricsRecorder` reads; the structural test moves from the recorder's tests to `test_policy`; acceptance 5 | ~340 lines, 11 files |
| 30 | `feat/webui-always-served` | D13, D15 for `webui.enabled`: the `if`, `WebuiConfig`, the default, the refusal, `_config()`, the crawl-only wiring test (the webui now starts there), the three YAML files, `operate.md`, `troubleshooting-start.md`, `AGENTS.md`'s WebUI row; commit `feat!:`; acceptance 7 for `webui.enabled` | ~120 lines, 11 files |
| 40 | `feat/node-metrics-on-the-webui` | D1 to D4, D7, D8, D12: the pair, `NodeMetricSample` in the Reader's port file (Corrected: in the domain module, since a driven read port returns domain types only and the driving port's listing holds samples), `InMemoryNodeMetricStore` with a few tests of its own (the contract comes in block 50), `ListNodeMetrics`, the route and the format, the composition, the dispatcher writing both; acceptance 2, 6 | 470 to 590 lines, 19 files: the chain cannot split (D12), the teammate trims to the bound |
| 50 | `test/node-metric-store-contract` | D10: `FakeNodeMetricStore`, the contract, the step tests through the Reader; acceptance 4 (Corrected: also, decided by the lead, block 40's tests that used `InMemoryNodeMetricStore` as a double use the fake, and the webui tests a `FakeNodeMetricLister`) | ~270 lines, 12 files |
| 60 | `test/node-metrics-against-the-old-output` | D11: the fixture and its comparison (Corrected: two fixtures); the wiring test (without `observability.metrics`) and the smoke read `/metrics` on 8080; acceptance 1, 3 | ~240 lines, 6 files |
| 70 | `feat/drop-prometheus-client` | D14, D15 for `observability.metrics`, What goes away: the recorder, its port, the spy, the 9090 server, the dispatcher's single writer, the dependency, `deploy/crawler.yml`, the smoke's refused 9090; commit `feat!:`; acceptance 7 for `observability.metrics`, 8 | 440 to 510 lines, 17 files: mostly deletions, the teammate trims to the bound |
| 80 | `docs/node-metrics-documents` | Documents but the lines block 30 took; acceptance 9 | ~90 lines, 5 files |
| 85 | `refactor/node-metric-labels` | D6's typed labels, from the operator's review of #492 (Corrected: added after approval, split from block 20): the label classes, the instructions refusing another class, the store and its fake keyed on the labels' pairs, the glossary and `architecture.md` | 276 lines, 11 files, measured |
| 90 | `docs/metrics-on-the-webui-closing` | Wrap: findings fixed, `BACKLOG.md` (the entry deleted, one added), the handoff | ~3 lines, 1 file (Corrected: 113 lines, 13 files against block 85, the holistic review's fixes being code and tests) |

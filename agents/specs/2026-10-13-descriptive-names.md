# Descriptive names

- Date: 2026-10-13. Status: approved by the operator on 2026-10-13, after the spec review
  (`.reviews/descriptive-names-spec.md`, 0 critical, 6 major, 15 minor, all answered).
- Tier: Spec, operator surfaces included (the operator, 2026-10-13).
- Origin: `BACKLOG.md`'s "Descriptive names", from
  https://github.com/mission-titar/p2pwatch/pull/198#discussion_r4261141305.
- Evidence: an audit of every `src/` tree by four agents on `f9783b4`; the spec review's probes. Paths under
  `packages/crawler/src/p2pwatch/` unless noted.

## At a glance

- **A "Naming" section in `AGENTS.md`**: rules and a glossary of the project's words, in every agent's context.
  The spec and holistic reviews check names against it. No lint.
- **One word per concept across the layers**: about twenty concepts change name (D4), over 300 symbols in all.
- **Operator surfaces renamed for the 5.0**: metric labels, three catalog columns, `crawler.yml` and
  `matcher.yml` keys, webui query keys (D5).
- **The webui's read side is redesigned in its own lot** (section 7); this lot touches it only where a renamed
  column forces it.
- **The executable detail is in the appendix**, for the teammates.

## 1. Why

The audit found few generic names like `what`, and mostly one concept under several names as it crosses layers:

- the search channel (`ed2k`, `kad`) is `channel` in the ports and `network` in the events and metrics, while
  `Network` is the file identity's namespace, where eD2k covers Kad;
- the aMule client's label is `endpoint.name`, `instance_name`, `client` or `name`, and `client` also names the
  port objects;
- a file's name goes `filename`, then `name`, then `filename` again;
- the matching engine calls its `FileCandidate`s `names`, where the crawler's `names` are strings.

The goal: a reader with partial context follows a value by its name, from a signature or a call site, and the
next agent does not reintroduce what this lot removes.

## 2. Scope

- **In**: every `src/` symbol the audit flagged (the appendix), the operator surfaces of D5, comments,
  docstrings and log messages that use a renamed word.
- **Out: the webui's read side** (section 7): its records, displays and reader, and the crawler's three
  observation shapes (`Sighting`, `ObservedFile`, `ReevalRow`). *Reason (operator): the webui handles
  persistence-shaped records in its domain, a defect larger than naming; renaming them now would rename them
  twice.* **Except** where a renamed column or SQL alias forces it: the SQL strings naming it, and the fields
  that mirror it (`Sighting.name`, `media_length_sec`, `directly_reachable`, the displays `high_id` and
  `on_network`). *Reason: a field left behind is a second name for the column's concept.*
- **Out: test names and test helpers**, except a fake implementing a renamed port method. *Reason: the priority
  is the data flow in `src/`.*
- **Out: locals beyond the audit's list.** *Reason: the operator ranked them last; the guideline covers them
  going forward.*
- **Behaviour changes**, each a test watched failing first: the refusal of every renamed YAML key; the metrics'
  labels and names; the start notification and the source alerts' texts; a root key's error text; the query
  keys and a redirect code; the nav label; three migrations; strict templates (D6); three defects (D8).

## 3. Decisions

### D1. The "Naming" section of `AGENTS.md`

Block 10 adds, after "Hard rules":

```markdown
## Naming

A name lets a reader with partial context tell, from a signature or a call site, what a value holds and what
a function does.

- **One concept, one name, in every layer.** A value keeps its name from where it enters to where it is read.
  An external name (an amuleapi field, a SQLite function's) is translated once, in its mapper or adapter, and
  kept from there. The glossary below fixes the shared words.
- **One name, one concept, within a package**: never a string in one function and a dict under the same
  name in the next.
- **Say what the value is, not its type or its role**: no `what`, `data`, `info`, `item`, `obj`, `result`,
  `value`, `entry`, `payload`; a single letter only inside a one-line comprehension or lambda.
- **A quantity carries its unit unless its type does**: `_seconds`, `_bytes`, `_mib`, `_micros`; a `datetime`
  or a `timedelta` needs none.
- **A boolean reads as a predicate**: `is_tracked`, `has_useful_point`, `clamped`, `enabled`.
- **A function says what it returns or does, side effects included**: `get_or_create_node_id`,
  `rejudge_file`. A class names what one instance is.
- **A mapping is `<values>_by_<key>`, a collection the plural of its element.**
- **`latest` is the most recent of a series; `last` only pairs with `first`.**
- **No abbreviation but the glossary's**, units and protocol names (`kbps`, `tcp`, `md4`, `ed2k`) aside.
- **Comments, docstrings and log messages use the code's words.**
- **The most telling word wins over the most widespread one**: an existing name is not a reason to keep it.

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
| `candidate` | a `FileCandidate`, one name of a file and its metadata, the matcher's input; a `DownloadCandidate` is a file with a download-tier decision | `names` |
| `target` | an episode segment to recover: `target_id`, `TargetSegment`, its `letter` | `segment` for the letter; Kad's keyword target, which is a `kad_word` |
| `tier` | a decision's strength: `catalog`, `notify`, `download` | `before`, `after` |
| `token` | a named matcher of the policy (`tokens:`) | a word of a text |
| `word` | a piece of normalized text | `token` |
| `reevaluation` | re-judging every file when the policy changed | `backfill` |
| `tracked` | a download with a row in `downloads`, whatever its state | `downloaded`, `active` |
| `wake` | `WakeHub` wakes the loops waiting on a subject | `signal`, `nudge` |
| `first useful`, `reappeared` | a source's two alerts | `new`, `useful again` |
| `error_label` | the label a parser prints in its errors | `what`, `label`, `field` |
| `micros` | an integer of microseconds: an instant counts from the epoch | a bare `_at` on an `int` |
| `id`, `db`, `sql`, `url`, `api`, `json`, `ecid`, `mib`, `iso`, `min`, `max`, `conf` | the abbreviations allowed (`conf`: aMule's `amule.conf`) | |
```

- *In `AGENTS.md` (operator): it is in every session and every teammate's context, so the words are there when
  an agent names something; a separate file is opened only by an agent that thinks of it.*
- *A glossary: most findings are a concept named differently across layers, which a rule cannot settle without
  the word to use.*
- *"The most telling word" is the operator's ruling on the wake hub (D4).*

### D2. The reviews check names

`agents/reviews/holistic.md` gains a twelfth point: "**Names.** Does every name the lot adds or renames follow
`AGENTS.md`'s Naming? A concept with two names across the diff, a name with two concepts, or a word the glossary
maps elsewhere is a finding." `agents/reviews/spec.md` gains: "**Every name a decision introduces follows
`AGENTS.md`'s Naming**, and a new concept gets its glossary line in the same lot." *Reason: a guideline nobody
checks decays, and these two reviews read every lot.*

### D3. No lint

pylint's `disallowed-name` with fifteen generic words and every single letter flags 66 names in 3.1 s, 42 of
them single letters (the command is in the appendix's evidence); ruff 0.16.9 has no such rule. *Reason
(operator): a word list catches the cheap class only; the main class, one concept under several names, needs
the glossary and a reviewer.*

### D4. The vocabulary

| Concept | Today | Becomes | Why |
|---|---|---|---|
| A client's search channel | `network` on 3 events and `record_observation` | `channel` | the multi-network spec's word; `network` is `Network` |
| A channel joined its network | `on_network` | `connected` | pairs with `connectable`; "network" had a third sense |
| A client's configured label | `endpoint.name`, `instance_name`, `name`, an event's `client` | `client_name` | `client` stays for the port objects |
| The aMule client unreachable | `InstanceUnreachable` | `ClientUnreachable` | beside `ClientUnreachableLasting` |
| The running p2pwatch | "instance online (mode observer)" | "node online (download off)" | "instance" meant the client too; the config says `download.enabled` |
| The download loop's wake-up | `DecisionSignal.signal()`, `signal_hub`, nudge | `WakeHub.wake()`, `wake_hub` | the operator: the most telling word |
| The repositories' clock | a callable aliased `Clock` beside the port `Clock` | the port `Clock` (D7) | one name, one concept; prepares the monotonic clock |
| Source alerts | `FirstUseful`/`UsefulAgain`, `SourceNew`/`SourceReappeared`, `new`/`reappeared` | `FirstUseful`/`Reappeared`, `SourceFirstUseful`/`SourceReappeared`, `first_useful`/`reappeared` | the operator: each states its condition; "new" is false for a source seen not useful |
| A file's name | `Sighting.name`, `known_names`, `best_name`, `names` | `filename`, `known_filenames`, `best_filename_and_size`, `filenames` | glossary |
| The most recent | `last_decisions`, `last_observation` | `latest_decisions`, `latest_observation` | "last" also reads as final or previous |
| Re-judging one file | `record_decision_if_changed(file, candidate)` | `rejudge_file(file, base_candidate)` | the operator: it judges the file for every target, then records what changed |
| A decision's tiers | `DecisionChange.before`, `after` | `previous_tier`, `new_tier` | only a comment said they were tiers |
| The startup re-judging | backfill, `last_backfill_policy` | reevaluation, `reevaluated_policy_fingerprint` | one word; it returns a fingerprint, not a policy |
| A backoff | `ChannelBackoff`, `WorkerPolicy` | `BackoffState`, `BackoffPolicy` | it also holds client-only keys; "policy" means the matcher's |
| A download with a row | `is_downloaded`, `active_states` | `is_tracked`, `tracked_states` | both cover failed and finished rows |
| A source's usefulness | `SourceGroup`, `role.group` | `SourceUsefulness`, `role.usefulness` | its values are useful, not useful, unknown |
| How old a carried role may be | `source_tolerance(spacing)` | `carried_role_max_age(time_between_reads)` | the operator; beside `carried_role` |
| The matcher's input | `names`, `name`, `c`, `fields` | `candidates`, `candidate` | `names` were strings elsewhere |
| A word of a text, in the matcher | token (`tokenize`) | word (`split_words`) | "token" is the policy's named matcher, operator-facing |
| A segment's letter | `TargetSegment.segment` | `letter` | `targets.yml` says `letter` |
| A parser's error label | `what`, `section`, `label`, `field` | `error_label` | `section` was a string in one parser, a dict in the next |
| Kad's keyword target | `_kad_target`, `target` | `_kad_word`, `kad_word` | "target" is an episode |
| The aMule boot step | the package `p2pwatch_amule.config` | `p2pwatch_amule.boot` | it runs the whole boot step, not only config |
| An advisory | `cve` | `advisory_id` | the registry holds CVE and GHSA ids |
| A metric instruction's kind | `MetricKind` (`inc`, `set`, `remove`) | `MetricOperation` | "kind" suggests counter or gauge |

**Kept on purpose**: `SearchFailedError`, since the event `SearchFailed` and the metric `p2pwatch_search_failures`
say "failed" too and a refused search is a failed one; the variant's `content_hash`, the column's and the SQL
function's name.

### D5. The operator surfaces

All ship in the 5.0, each a step in `docs/migration-4x.md`. A renamed YAML key is refused at boot with its new
name, like `_MOVED_KEYS`. *Reason (operator): 4.x is frozen but for an urgent hotfix, and the 5.0 already
breaks `crawler.yml`.*

| Surface | Today | Becomes | Why |
|---|---|---|---|
| Label of 5 metrics | `network` | `channel` | D4; `source_alerts{network}` keeps it, a `Network` |
| Metric | `p2pwatch_channel_on_network` | `p2pwatch_channel_connected` | D4 |
| `source_alerts{kind}` value | `new` | `first_useful` | D4 |
| catalog `source_observations` | `transfer_counter` | `session_received_bytes` | amuled's per-session byte counter, feeding `received_bytes` |
| catalog `source_variants` | `directly_reachable` | `connectable` | glossary (operator) |
| catalog `observation_variants` | `media_length_sec` | `duration_seconds` | amuleapi's name |
| `matcher.yml` coverage token and token override | `min`, `fuzz` | `min_coverage`, `min_similarity` | `min` is a bound under `attr_between`; `fuzz` names a library |
| `matcher.yml` placeholder | `{segment}` | `{letter}` | `targets.yml` says `letter` |
| `matcher.yml` `attr_between` | `size_mb`, `duration_sec` | `size_mib`, `duration_seconds` | the values are MiB; unused in `deploy/` today |
| `crawler.yml` notifications | `tag` | `audience` | its values are audiences |
| local.db | `backfill_state.policy_sha256` | `reevaluation_state.policy_fingerprint` | D4 |
| local.db `scheduler_state` key | `channel_backoff` | `backoff_states` | D4 |
| local.db `waiting_reason` | `local` | `local_processing` | it covers hashing, allocating, completing |
| webui query keys | `q`, `dir`, `target`, `name` | `search`, `direction`, `target_id`, `source_name` | unlisted abbreviations; `target` holds an id |
| webui redirect | `?done=restart` | `?done=restarted` | beside `paused`, `resumed` |

- **Catalog migration 0012** only renames the three columns with `ALTER TABLE ... RENAME COLUMN`, which rewrites
  the schema and the triggers, indexes and CHECKs naming them, and no row (SQLite's documentation; the spec
  review's probe on a version 11 catalog wrote only schema pages). So it needs no copy before it.
- **local.db migrations 0009 and 0010** rename the table and column, then update the key and the value; local.db
  holds no catalog data.
- **Old query keys are not redirected**: the webui is one operator's private viewer, who re-bookmarks once.
- **Kept**: `sort`, `tier`, `page`, `from`, `to`, `show_unmatched`; `download.reappeared_after_seconds`;
  `attr_between`'s `min` and `max`, qualified by the attribute beside them.

### D6. Strict templates

The webui's Jinja takes `StrictUndefined`. *Reason: today a template reading a missing name renders an empty
string, and the language server does not see templates, so a rename would blank a column silently.* The spec
review's probe: strict, the 324 webui tests pass on today's tree, and each of the templates' 154 attribute
accesses, renamed, fails a test. (Corrected: block 20 renamed each of the 209 attribute accesses one at a time;
three, in `{% else %}` branches, failed no test. Block 20 tests the two reachable ones; the third,
`sources.html:26`, is dead, since a `/sources` row always has a user hash.) It is block 20, before any rename a
template reads.

### D7. The repositories take the `Clock` port

The alias in `persistence_sqlite/connection.py` goes; the three SQLite repositories take the port, with no
default, and call `clock.now()`. *Reasons: one name for one concept; a now-only protocol would be a second clock
concept, which the monotonic clock's lot will decide; a default would need a third clock object.*

### D8. Three defects fixed on the way

`coverage_for` never reads its `target_id`; the template key `title_by_id` is read by no template;
`SearchKeyword.origin` is always its `text` and read by no `src/` code. Each goes. *Reason: defect class 1, and a
misleading name in itself.*

## 4. Blocks

| # | Branch | Holds |
|---|---|---|
| 10 | `docs/naming-guidelines` | this spec, D1, D2 |
| 20 | `refactor/strict-webui-templates` | D6 |
| 30 | `refactor/channel-client-node` | channel, connected, client name, node |
| 40 | `refactor/wake-hub` | the wake hub |
| 50 | `refactor/clock-port` | D7, the adapters' micros |
| 60 | `refactor/decisions-filenames` | decisions, filenames, latest |
| 70 | `refactor/reevaluation` | reevaluation, local.db 0009 |
| 80 | `refactor/backoff-downloads` | backoff, tracked downloads, local.db 0010 |
| 90 | `refactor/sources-columns` | sources, alerts, catalog 0012 |
| 100 | `refactor/observability-names` | the policy, status loop, notifications, `audience` |
| 110 | `refactor/config-parsing-names` | `error_label` |
| 120 | `refactor/crawler-names` | the crawler's other names, Kad |
| 130 | `refactor/webui-names` | the query keys, the webui's composition, D8 |
| 140 | `refactor/matching-names` | the matcher and its YAML keys |
| 150 | `refactor/package-names` | amule, amule_bump, vex_guards |
| 160 | `docs/descriptive-names-wrap` | the closing block |

- **Cut by concept; a rename block may pass a bound** (the review estimates up to 45 files for block 90).
  *One-line reason (operator): a mechanical rename is read by its mapping, not file by file, so splitting it
  multiplies pull requests and CI runs without making it more readable.* A block's other content (a migration,
  a refusal) stays within the bounds.
- **Order**: the guideline first, so every teammate reads it; strict templates before any rename a template
  reads; then the data's way in, from the client to the matcher.
- **Strict TDD**: a pure rename adds no test; each behaviour change of section 2 is watched failing first.
- **Between blocks**, old and new names of different symbols may coexist, never two names for one symbol.

## 5. Acceptance

- **The guideline**: `AGENTS.md`'s Naming holds D1's 22 glossary rows, and both mandates name
  "`AGENTS.md`'s Naming". Wrong if either is missing.
- **No old name survives**: per block, Serena's `find_symbol` finds none of the appendix's old Python names,
  and `git grep -nwF` finds none of its **Strings** outside applied migrations, their tests,
  `docs/migration-4x.md` and the refusals. The banned prose (`backfill`, `nudge`, `useful again`) is gone from
  `src/`. Wrong if one is found.
- **The metrics**: the registry shows `("client", "channel")` on the five metrics,
  `p2pwatch_channel_connected`, `("network", "kind")` on `source_alerts`, and `kind="first_useful"` after a
  first-useful alert.
- **The migrations**: after 0012, a version 11 catalog's schema SQL equals the old one with the three names
  substituted, its values are equal, and 0012 holds only `RENAME COLUMN`s; after 0009 and 0010, local.db reads
  back the same fingerprint, `backoff_states` and `local_processing`.
- **The YAML keys**: each old key is refused with its new name.
- **The webui**: each new query key filters or sorts and its old key does not, on `/files` and `/sources`; a
  restart redirects to `?done=restarted`; a bare `{{ missing }}` and an absent attribute raise
  `UndefinedError` through `build_app`'s templates.
- **The texts**: the start notification, the two alert titles and the reappeared body read as D4; a root key's
  error has no `crawler.` prefix; the nav reads "Node".
- **The gate** and `uv run poe docs-build` pass at every block's tip.

## 6. Risks and pitfalls

- **The language server does not see strings**: SQL, Jinja keys, YAML keys, texts, docs, and names tests patch
  by string (`"build_app"`). Each block lists them under **Strings**.
- **A Protocol method's rename does not reach its implementations**: pyright links them structurally, so each
  adapter and fake is renamed on its own; `mypy --strict` catches a miss where one is passed as the port.
- **`matcher.yml`'s attribute names are `FileCandidate`'s fields** (`getattr`, `ATTR_NAMES`): both change in
  block 140.
- **Serena reads `[tool.pyright]` only when it starts**: a teammate whose rename finds no test reference
  restarts it.
- **Dashboards, alert rules and SQL console queries on a renamed surface break at the 5.0**:
  `docs/migration-4x.md` lists each.

## 7. Adjacent backlog items, and the deferred read side

- **Stage 5, new networks**: stays open; the glossary fits any client.
- **Sort the files view by first seen**, **the webui in the visitor's time zone**: stay open, in the read side's
  lot.
- **A copy before a migration that rewrites rows**: stays open and required before the release; 0012 rewrites
  no row.
- **A monotonic clock**: stays open; D7 prepares it.
- **Descriptive names**: deleted at Wrap.
- **The webui's read side**: added at Wrap, with the operator's direction (2026-10-13): its own read-only
  connection and read repositories behind its own ports; one domain abstraction of an observation, into which
  `Sighting`, `ObservedFile` and `ReevalRow` collapse; no persistence type above the adapters, instants as domain
  types; a reader returns `<Thing>Record` or `<Thing>DetailRecord`, a template receives `<Thing>Display` or
  `<Thing>DetailDisplay`, in `records.py` and `displays.py` (*`Summary` and `Detail` alone read as ready to
  render, which is what `Display` marks*). It inherits the names this lot leaves there: `query` and `dir` in
  `catalog_read.py`, `_PAGE_SIZE`, `_ISO`, and the audit's record and display names.

## Appendix: inventory per block, for the teammates

`old → new`, by module. A field rename includes its constructor keywords; a port method's rename includes every
implementation and fake. "Drop" deletes the symbol. **Strings** lists the old names the language server cannot
see, which section 5's check greps.

### Block 30: channel, client, node

- `domain/observability/events.py`: `SearchExecuted.network`, `SearchFailed.network`,
  `ObservationRecorded.network` → `channel`; every `client: str` field → `client_name`; `InstanceUnreachable` →
  `ClientUnreachable`; `CrawlerStarted.mode` → `download_enabled: bool`; `SearchExecuted.n_results` →
  `result_count`; `ChannelStatusSampled.on_network` → `connected`.
- `application/record_observations.py`: `record_observation(client=, network=)` → `client_name=`, `channel=`.
- `application/search_worker.py`: `instance_name`, `_instance` → `client_name`, `_client_name`;
  `_record(channel, results)` → `_record_observations(channel, observations)`.
- `application/status_loop.py`: `StatusLoopDeps.name` → `client_name`; `StatusBoard(clients)` → `client_names`.
- `application/run_download_cycle.py`: `DownloadDeps.client` → `download_client`; the docstring's `instance=`
  label (`:419-423`) → `client=`.
- `domain/observability/policy.py`: `_search_labels`, `_channel_gauge` read `channel`; the label key `network`
  → `channel` (D4); `ChannelField`'s `on_network` → `connected`; the start notification (D4).
- `adapters/observability/prometheus_sink.py`: the five label tuples and the metric name (D4).
- `adapters/config/crawler_config.py`: `AmuleEndpoint.name` → `client_name`, `AMULE_INSTANCE_NAME` →
  `AMULE_CLIENT_NAME`.
- `adapters/mule_api/mapping.py`: `_channel(name, network, connectable)` → `_channel(channel, channel_json,
  connectable)`.
- `ports/client_status.py`: `ClientReading` → `StatusReading`, `ChannelStatus.on_network` → `connected`;
  `ports/scheduler_state_repository.py`'s docstring "instance / instance:channel" → "client / client:channel".
- `composition/app.py`: `ClientFactory`, `default_client_factory` → `MuleClientFactory`,
  `default_mule_client_factory`; `CrawlerStarted(download_enabled=...)`.
- `webui/composition/app.py` and `dashboard.html`: the channel line reads `connected`.
- The prose of D4.
- Documents: `docs/operate.md` (metrics, the start notification), `docs/migration-4x.md`.
- **Strings**: `p2pwatch_channel_on_network`, `instance online`, `"network"` in `prometheus_sink.py`'s first
  five tuples, `on_network` in templates and docs.

### Block 40: the wake hub

D4, every site: the port, its asyncio adapter, `WorkerDeps`, `DownloadLoopDeps`, `record_observation`,
`reevaluate_catalog`, `record_decision_if_changed`, `CrawlerApp(signal_hub=)` and `self._signal`, the fakes, the
prose, `docs/contributing/architecture.md:231`. **Strings**: `nudge`, `DecisionSignal` in docs.

### Block 50: the clock port

D7, and in the same adapters the integers of microseconds: `catalog_repository.py:125` `observed_at` →
`observed_at_micros`; `source_repository.py` `now` (`:107`, `:124`, `:140`) → `read_at_micros`, `_tolerance` →
`_carried_role_max_age_micros`; `clock_asyncio.py:33` `_jitter` → `_random`.

### Block 60: decisions and filenames

- `application/decisions.py`: `record_decision_if_changed(file, candidate)` → `rejudge_file(file,
  base_candidate)`; `names` → `filenames`.
- `ports/catalog_repository.py` and its adapter: `last_decisions` → `latest_decisions`, `last_observation` →
  `latest_observation`, `download_decisions` → `download_candidates`.
- `domain/observation.py`: `Sighting.name` → `filename`; `persistence_sqlite/sightings.py:24` `AS name` →
  `AS filename`, `:26` `source_count_max` → `source_count` (it holds the latest observation's count, not a
  maximum, `:41-45`); `known_names` → `known_filenames`, `best_name` → `best_filename_and_size`; the read side's
  SQL strings and readers that name them (section 2).
- `domain/observability/events.py`: `DecisionChange.before`, `after` → `previous_tier`, `new_tier`;
  `DownloadCompleted.targets`, `SourceNew.targets`, `SourceReappeared.targets` → `target_titles` of
  `TargetTitle`s; `run_download_cycle.py:183` `_targets` → `_target_titles`.
- **Strings**: `obs.name`, `source_count_max`, `known_names`, `best_name` in SQL and docs.

### Block 70: reevaluation

- `application/run_backfill.py` → `application/reevaluate_if_policy_changed.py`, its function likewise, its
  `run_backfill` parameter → `reevaluate`, its `policy_fingerprint` stays.
- `ports/local_state_repository.py` and its adapter: `last_backfill_policy`, `set_last_backfill_policy(sha256)`
  → `reevaluated_policy_fingerprint`, `set_reevaluated_policy_fingerprint(fingerprint)`; `node_id()` →
  `get_or_create_node_id()` (it creates and persists the id on the first call); `generated` → `node_id`.
- `application/reevaluate_catalog.py`: `ReevalSummary` → `ReevaluationSummary`, `evaluated`, `written` →
  `files_evaluated`, `rows_written`.
- The prose's "backfill".
- local.db migration 0009: `ALTER TABLE backfill_state RENAME TO reevaluation_state` and `RENAME COLUMN
  policy_sha256 TO policy_fingerprint`.
- **Strings**: `backfill`, `policy_sha256` (outside the applied migrations and their tests).

### Block 80: backoff and downloads

- `ports/scheduler_state_repository.py` and its adapter: `ChannelBackoff` → `BackoffState`,
  `load_channel_backoff`, `save_channel_backoff` → `load_backoff_states`, `save_backoff_states`; the stored key
  `channel_backoff` → `backoff_states`.
- `application/search_worker.py`: `WorkerPolicy` → `BackoffPolicy` (fields without `backoff_`),
  `BackoffRegistry._states` → `_state_by_key`, `key` → `backoff_key`, `remaining` → `seconds_remaining`;
  `composition/app.py:162` `_build_policy` → `_backoff_policy`.
- `application/run_download_cycle.py` and `persistence_sqlite/download_repository.py`: `is_downloaded` →
  `is_tracked`, `active_states` → `tracked_states`, `expire_lost(max_age_seconds)` → `lost_after_seconds`,
  `get_target_id` → `queued_target_id`, `CatalogReader` → `DownloadCatalogReader`, `listed` →
  `listed_statuses` or `listed_files` (by type), `outstanding`, `free` → `outstanding_bytes`, `free_bytes`,
  the local `target` (`:177`) → `wanted_state`, `_monitor` → `_reconcile_states`, `_AlertRound.alerting` →
  `alerts_allowed`, `edge` → `disk_low_edge`, `_INSERT` → `_INSERT_QUEUED`.
- `ports/download_client.py`: `DownloadStatus.bytes_total` → `size_bytes`; `WaitingReason.LOCAL` →
  `LOCAL_PROCESSING`; `mule_api/mapping.py:139` builds `DownloadStatus` by keyword.
- `composition/app.py:227` `_build_download_loop` → `_build_download_deps`.
- local.db migration 0010: the `scheduler_state` key and the `waiting_reason` value (D5).
- Documents: `docs/operate.md:328` (the `local` waiting reason), `docs/migration-4x.md`.
- **Strings**: `channel_backoff`, `'local'` as a waiting reason.

### Block 90: sources and the catalog columns

- `domain/source.py`: `SourceGroup` → `SourceUsefulness`, `.group` → `.usefulness`; `source_tolerance(spacing)`
  → `carried_role_max_age(time_between_reads)`; `SourceReading.key` → `source`; `directly_reachable` →
  `connectable`; `transfer_counter` → `session_received_bytes`.
- `ports/source_repository.py`: `RecordedReading.key` → `source`; `EarlierPoints.useful` → `has_useful_point`.
- `persistence_sqlite/source_repository.py`: `spacing` → `time_between_reads`, the local `key` holding a content
  hash → `variant_content_hash`, `point` (`:104`) → `contact_point`, `_carried_from` → `_latest_point_role`,
  `_variant` → `_variant_columns`; `catalog_repository.py:124` `key` → `variant_content_hash`.
- `application/source_alerts.py`: `UsefulAgain(absent)` → `Reappeared(absent_for)`, `earlier` →
  `earlier_points`; events `SourceNew` → `SourceFirstUseful`, `.name` → `source_name`; the label value, the
  titles and the body (D4).
- `composition/app.py:156` `_sources_spacing` → `_time_between_source_reads`.
- `media_length_sec` → `duration_seconds` in `FileObservation`, `Sighting`, `ReevalRow`,
  `candidate_from_fields(media_length_sec)` (`domain/observation.py:19`), `content_hash(media_length_sec)`
  (`persistence_sqlite/variants.py:22`), `MatchingExplainer.explain` (`webui/adapters/matching_read.py:43`).
- The read side's fields of section 2: `SourcePeriodView.directly_reachable`, `SourceHistoryRow.high_id` and
  its template key.
- catalog migration 0012: the three `RENAME COLUMN`s (D5), and nothing else; every SQL string naming them
  (`merge/merger.py`'s copy statements, `webui/adapters/catalog_read.py`, `sightings.py`).
- Documents: `docs/contributing/architecture.md`, `docs/migration-4x.md`, `docs/operate.md` (the alerts).
- **Strings**: `transfer_counter`, `directly_reachable`, `media_length_sec`, `high_id` outside the mapper,
  `useful again`, `New source`.

### Block 100: observability and notifications

- `domain/observability/policy.py`: `MetricKind`, `kind` → `MetricOperation`, `operation`; `Report.notification`,
  `title` → `notification_body`, `notification_title`; `_channel_alert(severity, event, what)` and
  `_describe_source(event, kind, what, title)` → `state_phrase`, `alert_kind`, `notification_title`;
  `_DEGRADED`, `_RECOVERED` → `_DEGRADED_PHRASE_BY_FIELD`, `_RECOVERED_PHRASE_BY_FIELD`; `_word` → `_yes_no`.
- `domain/observability/events.py`: `ChannelDegraded.seconds`, `ClientUnreachableLasting.seconds` →
  `degraded_for_seconds`, `unreachable_for_seconds`.
- `application/status_loop.py`: `_Watch.read(good, now)` → `_AlertTimer.observe(healthy, now)`;
  `CHANNEL_ALERT_SECONDS`, `UNREACHABLE_ALERT_SECONDS`, `CURRENT_FOR_SECONDS` → `CHANNEL_ALERT_AFTER_SECONDS`,
  `UNREACHABLE_ALERT_AFTER_SECONDS`, `READING_FRESH_FOR_SECONDS`; locals `api`, `channels`, `watch` →
  `api_timer`, `channel_timers`, `_observe`.
- `adapters/observability/dispatcher.py`: `notify_timeout_seconds`, `_timeout` → `notification_timeout_seconds`;
  `apprise_notifier.py`: `NotificationTargets` → `AppriseTargets`, `_prefixed`, `_bare` → `_prefixed_group`,
  `_bare_group`; apprise's own `tag=` keyword (`:66`, `:77`) stays.
- `adapters/config/crawler_config.py`: `NotificationTarget.tag` → `audience`, the YAML key with it and its
  refusal (D5); `deploy/crawler.yml:36`, `:39`; `docs/operate.md:171`.
- **Strings**: `tag:` in YAML and docs (apprise's keyword aside).

### Block 110: config parsing

- `adapters/config/crawler_config.py`: `section: str`, `label`, and `interpolation.py`'s `field` →
  `error_label`; a sub-mapping is `section`, the root `document`; one parameter order
  `(section, key, error_label, default)`; `_A_DAY`, `_THIRTY_DAYS` → `_A_DAY_SECONDS`, `_THIRTY_DAYS_SECONDS`;
  `_require_str` → `_string`; `result` (`:390`) → `parsed_keywords`; `place` (`:447`) → `new_path`;
  `interpolation.py` `_PATTERN` → `_ENV_REFERENCE`.
- The error prefix `crawler.` printed for root keys (`:460-463`) names a path that does not exist in
  `crawler.yml`: the root keys print bare.

### Block 120: the crawler's other names

- `domain/search/keywords.py`: `generate_keywords` → `dedupe_keywords`, `SearchKeyword.origin` dropped (D8).
- `domain/download/policy.py`: `download_policy(file_size)` → `decide_download(size_bytes)`.
- `application/search_tasks.py`: `SearchTasks` → `SearchTaskRunner`.
- `composition/app.py`: `status` (`:332`) → `status_board`, `obs` (`:418`) → `observability`, `_human` →
  `_print_progress`; `composition/__main__.py:59` `build_app` → `build_crawler_app`, with the tests that patch it
  by the string `"build_app"` (`tests/composition/test_main.py:107`, `:124`, `:139` and others).
- `merge/merger.py`: `sources`, `dest_is_source` → `source_catalogs`, `output_is_source`; `_STATEMENTS` →
  `_COPY_STATEMENTS`; `_merge_one` → `_merge_catalog`.
- `adapters/mule_api/client.py`: `timeout` → `timeout_seconds`; `_collect(path, envelope, identity)` →
  `_collect(path, list_key, keyset_column)`; `_request` → `_send_with_relogin`; `skipped_entries_total` →
  `skipped_results`; the Kad names of D4.
- `adapters/mule_api/mapping.py`: `source_ecid` → `offering_source_ecid`; `_int` → `_int_or_zero`; the locals
  `ed2k_hash` → `native_id`; `_ASKED` → `_ASKING_RELATIONS`, `_object` → `_as_dict`, `_sources` →
  `_source_counts`; `errors.py` `_envelope` → `_error_code_and_message`.
- `adapters/persistence_sqlite`: `connection.py:84` and `variants.py:54` `register`, `register_functions` →
  `register_sql_functions`.
- **Strings**: `"build_app"` in tests.

### Block 130: the webui

- The query keys and the redirect code (D5), in `webui/composition/app.py`, the templates and
  `docs/operate.md:283-288`.
- `webui/composition/app.py`: `query` → `search_text` for the search text, `query_params` for the request's;
  the kept parameters (`filters`, `sort_dir`, `summary_base`, `filter_query`, `facet_base`, `base`,
  `hidden_state`, `kept`, `named`, `query`, `params`) → `kept_params`, qualified at the call site; `dir`,
  `dir_param`, `next_dir`, `_normalize_dir` → `direction`, `direction_param`, `next_direction`,
  `_normalize_direction`; `_COLUMN_DEFAULT_DIR` → `_DEFAULT_DIRECTION_BY_COLUMN`; `_FLIP` →
  `_OPPOSITE_BY_DIRECTION`; `target_param` → `target_id_param`; `build_app(targets=)` → `target_segments=` (the
  alias `target_segments = targets` goes); `catalog_db`, `local_db` → `catalog_db_path`, `local_db_path`;
  `raw_id` → `source_id_hex`, `file_id_hex`; `_SORT_LABELS` → `_SORTABLE_COLUMNS` (and its stale comment);
  `_sort_header(col, label, sort, direction, filters)` → `(column_key, label, active_sort, active_direction,
  kept_params)`; `_tier_facets(counts, base)` → `(file_count_by_tier, kept_params)`; `_page_nav(page, n_rows,
  base_path, query)` → `(page, row_count, base_path, kept_params)`; `_build_summary` → `_files_summary(
  matched_count, total_count, show_unmatched, kept_params)`; `_interval` → `_now_and_interval`; `_normalize` →
  `_normalize_param`; `_CONSOLE_DB_LABELS`, `db` → `_CONSOLE_DBS`, `db_key`; the context keys `rows`, `headers`,
  `crawl` → `coverage_rows`, `sort_headers`, `crawl_state`; `status: StatusReadings` → `status_readings`,
  `client = reading.status` → `client_status`; `link` (`:849`) → `ed2k_link`; `_CUT_NOTICE` →
  `_CLAMPED_NOTICE`; `title_by_id` dropped (D8); the nav label "Nodes" → "Node" (`:111`; the route and its page
  say "Node").
- `webui/domain/interval.py`: `MAX_SPAN`, `PRESETS` → `MAX_INTERVAL_SPAN`, `INTERVAL_PRESETS`; `last(span, now)`
  → `interval_ending(now, span)`; `Interval.cut` → `clamped`.
- `webui/domain/coverage.py`: `coverage_for(target_id, decisions)` → `coverage_of(decisions)` (D8).
- `webui/domain/format.py`: `seasonal_id` → `seasonal_locator`.
- Nothing else of the read side (section 2): `catalog_read.py`'s `query` and `dir` parameters wait for its lot.
- **Strings**: `?q=`, `&q=`, `dir=`, `target=`, `name=` as query keys, `done=restart`, `"Nodes"`, the old
  context keys in templates.

### Block 140: matching

- `engine.py`: `names`, `name`, `c`, `fields` holding `FileCandidate`s → `candidates`, `candidate`; `_names()`
  → `_matchable_candidates()`; `evaluate_all` → `evaluate_file`; `_TIER_RANK` dropped (an alias of
  `config.TIER_RANK`); `_Match` → a `NamedTuple` `_RuleHit(resolved, rule_index, rule_name, tier, candidate)`;
  `best` → `best_by_target_id` (`:186`), `best_key` (`:238`); the comprehension letters `n`, `m`, `v`, `c`
  (`:120-126`) → `token_name`, `matcher`, `veto`, `candidate`.
- `matchers.py`: `KeywordMatcher._tokens` → `_phrase_words`, `CoverageMatcher._reference_tokens` →
  `_reference_words`, `candidate_tokens` → `filename_words`, `CoverageMatcher.value` → `coverage`, `min`,
  `fuzz` → `min_coverage`, `min_similarity`; `AttrBetweenMatcher(min=, max=)` → `min_bound`, `max_bound`;
  `_re` → `_compiled`; `ATTR_NAMES` takes `size_mib`, `duration_seconds`.
- `normalization.py`: `tokenize` → `split_words`; `_common_fold` merged into `fold`.
- `config.py`: `CoverageDef.min`, `.fuzz`, `TokenRef.min`, `.fuzz` → `min_coverage`, `min_similarity`;
  `AttrBetweenDef.min`, `.max` → `min_bound`, `max_bound` (the YAML keys `min`, `max` stay, D5).
- `models.py`: `TargetSegment.segment` → `letter`; `FileCandidate.size_mb`, `duration_sec` → `size_mib`,
  `duration_seconds`.
- `resolver.py`: `ResolvedTarget.tokens`, `.rules` → `matcher_by_token_name`, `matcher_by_rule_name`;
  `resolve_all` → `resolve_target`; `min_override`, `fuzz` override → `min_coverage_override`,
  `min_similarity_override`; `text` (`:106`) → `reference_text`.
- `validation.py`: `ConfigError` → `MatchingConfigError`; `what` → `error_label`; `_require_float` →
  `_optional_float`; `_operand_refs`, `_def_refs` → `_operand_token_names`, `_def_token_names`;
  `_check_overrides_target_coverage` → `_check_overrides_only_on_coverage`; in `parse_targets` (`:448-477`), `ep`
  → `episode_mapping`, `seg_list` → `segment_entries`, `seg` → `segment_entry`, `seg_map` → `segment_mapping`,
  `result` → `parsed_segments`; the refusals of `min`, `fuzz` on a `coverage` token and a token reference, of
  `{segment}`, of `size_mb` and `duration_sec` (D5).
- `interpolation.py`: the placeholder `{segment}` → `{letter}`.
- Crawler: `domain/observation.py` builds `size_mib=`, `duration_seconds=`; `webui/adapters/matching_read.py`
  `fields`, `names` → `base_candidate`, `candidates`; `composition/__main__.py`'s `MatcherConfigError` alias goes.
- `deploy/matcher.yml` (`title_hit`'s `min` at `:42`, `segment_id`'s `{segment}` at `:34`), the matching golden
  corpus, the documents that show the policy.
- **Strings**: `fuzz`, `{segment}`, `size_mb`, `duration_sec` in YAML, docs and fixtures; `min:` on a coverage
  line.

### Block 150: the other packages

- amule: the package `p2pwatch_amule.config` → `p2pwatch_amule.boot`, in every file naming it
  (`git grep -l 'p2pwatch_amule\.config' -- . ':!agents/*'`: 13 files, among them `packages/amule/docker/`'s
  entrypoint, `AGENTS.md`, `docs/contributing/amule-bump.md`, `docs/contributing/architecture.md`,
  `docs/troubleshooting.md`, `packages/amule_bump/src/amule_bump/body.py` and its test); `conf.py` `listen_port`
  → `tcp_listen_port`, `DEFAULT_PORT` → `DEFAULT_TCP_PORT`, `reconcile_conf(existing)` → `existing_conf`, one
  `AMULE_CONF_PATH` instead of `port_sync/__main__.py:17` `CONF_PATH` and `config/__main__.py:78` `conf_path`;
  `_missing(lookup)` → `_amule_account_missing`; `port_sync/__main__.py` `config` → `port_sync_settings`,
  `last_restart`, `now` → `latest_restart_monotonic`, `now_monotonic`, `configured`, `temporary` →
  `configured_port`, `temporary_path`; `port_sync` (a bool), `owned`, `PORT_SYNC_DOWN` → `port_sync_enabled`,
  `owned_directories`, `PORT_SYNC_DOWN_FILE`.
- amule_bump: `_arg_line` → `_arg_line_pattern`; `GITHUB_BODY_LIMIT`, `CHANGELOG_LIMIT`, `DIFF_LIMIT` →
  `GITHUB_BODY_MAX_CHARACTERS`, `CHANGELOG_MAX_CHARACTERS`, `DIFF_MAX_CHARACTERS`; `build_body` →
  `build_pull_request_body`; `latest_release` → `latest_release_tag`; `_announce` → `_write_step_outputs`;
  `dockerfile` (the text) → `dockerfile_text`, `target` → `git_object`, `name` → `full_name`, `TRUNCATED` →
  `TRUNCATION_NOTICE`.
- vex_guards: `Violation.cve` and every `cve` → `advisory_id`; `DebPackage` → `DpkgPackage`; `PackageAbsent`,
  `PackageMinVersion` → `DpkgPackageAbsent`, `DpkgMinVersion`; `DeclaredMinVersion.package` → `component`;
  `SubprocessDenies` → `ProgramNeverInvoked`; `source_scan.evaluate` → `evaluate_source_guards`; the letters
  `v`, `p`, `g` → `violation`, `problem`, `guard`; `_rel` → `_repository_relative`; `declared` →
  `declared_components`; `raw` (`check_image_claims.py:46`) → `unlocated`.
- **Strings**: `p2pwatch_amule.config` outside `agents/`.

### Evidence and exact commands

- **D3**: `uvx --quiet pylint==3.3.7 --disable=all --enable=disallowed-name
  --bad-names=what,data,info,item,items,obj,result,results,thing,tmp,temp,stuff,res,ret,val
  --bad-names-rgxs='^_?[a-z]$' --score=n packages/*/src`, counted with `grep -c disallowed-name` (66) and
  `grep -cE 'Disallowed name "_?[a-z]"'` (42), 2026-10-13; `ruff rule PLC0104` answers "invalid value" on ruff
  0.16.9.
- **D5, migration 0012**: https://www.sqlite.org/lang_altertable.html, "ALTER TABLE RENAME COLUMN". The spec
  review's probe: on a version 11 catalog from `open_catalog`, one row per table, the three renames in one
  transaction wrote WAL frames for `sqlite_schema` pages 1, 16 and 17 only (`dbstat`), the values stayed equal,
  `integrity_check` returned `ok`, and the append-only trigger and the renamed `CHECK (transfer_counter >= 0)`
  still fired (SQLite 3.49.1). `waiting_reason` has no CHECK (`migrations/local/0008_downloads_lifecycle.sql:9`).
  `transfer_counter` is fed by `downloaded_bytes_session` (`mule_api/mapping.py:179`).
- **D6**: Starlette 1.7.0's `Jinja2Templates.__init__` takes `env` (`uv run python -c "import inspect; from
  starlette.templating import Jinja2Templates; print(inspect.signature(Jinja2Templates.__init__))"`);
  `webui/composition/app.py:612` passes no `undefined`; `template-check` checks logic, not names
  (`webui/_dev/check_templates.py`).
- **D7**: the repositories at `catalog_repository.py:102`, `download_repository.py:67`,
  `local_state_repository.py:32`; composition passes `CrawlerApp`'s clock (`composition/app.py:199`); the
  migration tests, `tests/application/conftest.py`, `test_app.py` and the persistence tests' callable clocks
  (`_FakeClock`, `_SettableClock`, `_AdvancingClock`) pass a `Clock` instead.
- **D8**: `webui/domain/coverage.py:14-29`; `webui/composition/app.py:904`, and `grep -rn title_by_id
  packages/crawler/src/p2pwatch/webui --include='*.html'` finds nothing; `SearchKeyword.origin`: Serena's
  `find_referencing_symbols` finds one writer and two tests.
- **The read side's forced edits** (section 2): the SQL at `webui/adapters/catalog_read.py:61`, `:63`, `:165`,
  `:166`, `:409` and `persistence_sqlite/sightings.py:24`, `:26`; `.name` on a `Sighting` at
  `webui/composition/app.py:204`, `:852`; `SourcePeriodView.directly_reachable` (`views.py:161`); the displays
  `SourceHistoryRow.high_id` and `ChannelLine.on_network` with their template keys.
- **The prose**: `git grep -i -w -c <word> -- 'packages/*/src/*' ':!*/migrations/*'` gives `instance` 22 lines in
  10 files, `backfill` 20 in 10, `nudge` 24 in 7, `useful again` 3 in 2. Block 30's report lists each remaining
  `instance`, a Python object instance.
- **Section 5's string check**: `git grep -nwF '<string>' -- packages deploy tests/smoke docs ':!*/migrations/*'
  ':!packages/crawler/tests/**/*migration*' ':!packages/crawler/tests/**/older_catalog.py'
  ':!docs/migration-4x.md'`, which may print only the refusal naming the string and that refusal's test.

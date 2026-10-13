# Handoff: descriptive names, one concept one name across the layers

Drafted by block 150 from the lot's block reports (#200 to #215), corrected by the closing block 160.

## State

Tier Spec lot, operator surfaces included, spec `agents/specs/2026-10-13-descriptive-names.md` (approved
2026-10-13 after the spec review `.reviews/descriptive-names-spec.md`: 0 critical, 6 major, 15 minor, all
answered). Sixteen blocks, one stack cut from `main` at `f9783b4`: #200 (10, `docs/naming-guidelines`),
#201 (20, `refactor/strict-webui-templates`), #203 (30, `refactor/channel-client-node`), #204 (40,
`refactor/wake-hub`), #205 (50, `refactor/clock-port`), #206 (60, `refactor/decisions-filenames`), #207
(70, `refactor/reevaluation`), #208 (80, `refactor/backoff-downloads`), #209 (90,
`refactor/sources-columns`), #210 (100, `refactor/observability-names`), #211 (110,
`refactor/config-parsing-names`), #212 (120, `refactor/crawler-names`), #213 (130,
`refactor/webui-names`), #214 (140, `refactor/matching-names`), #215 (150, `refactor/package-names`),
then the closing block 160 (`docs/descriptive-names-wrap`), which holds the holistic review's fixes,
`BACKLOG.md` and this handoff.

Nothing of the stack is merged. `git tag -l 'v*'` still ends at `v4.1.0`; the node runs 4.1.0.
`catalog.db` goes to schema version 12 (`catalog/0012`, three `RENAME COLUMN`s); `local.db` to 10
(`local/0009`, `local/0010`).

Once merged, `AGENTS.md`'s Naming section fixes the project's words, both review mandates check names
against it, and every symbol of the spec's appendix carries its glossary name, from the amuleapi mapper
to the matcher, the webui and the three other packages.

## What was built

- **The guideline** (block 10): `AGENTS.md`'s "Naming", byte-identical to D1 (rules and 22 glossary
  rows, 23 once the closing block adds `audience`); `agents/reviews/holistic.md` gains its twelfth point,
  `agents/reviews/spec.md` its naming line (D2). No lint (D3).
- **Strict templates** (block 20): the webui's Jinja takes `StrictUndefined` (D6), autoescape kept. A
  template reading a missing name or attribute raises `UndefinedError`.
- **Channel, client, node** (block 30): `channel` on three events, `record_observation` and five metrics'
  labels; `connected` for `on_network` (metric `p2pwatch_channel_connected`, dashboard column);
  `client_name` for every label of the aMule client; `ClientUnreachable`; `StatusReading`;
  `MuleClientFactory`; the start notification "node online (download on|off)" from
  `CrawlerStarted.download_enabled`.
- **The wake hub** (block 40): `WakeHub.wake()`, `wake_hub`, the port and adapter modules renamed with
  them; "nudge" gone from `src/`.
- **The clock port** (block 50): the three SQLite repositories take `Clock` with no default (D7);
  `utc_now` deleted; the adapters' integers of microseconds end in `_micros`.
- **Decisions and filenames** (block 60): `rejudge_file(file, base_candidate)`, `latest_decisions`,
  `latest_observation`, `download_candidates`; `Sighting.filename`, `known_filenames`,
  `best_filename_and_size`; `DecisionChange.previous_tier`, `new_tier`; events carry `target_titles` of
  `TargetTitle`s.
- **Reevaluation** (block 70): `reevaluate_if_policy_changed`, `ReevaluationSummary`,
  `reevaluated_policy_fingerprint`, `get_or_create_node_id`; local.db 0009 renames `backfill_state` to
  `reevaluation_state` and `policy_sha256` to `policy_fingerprint`. "backfill" gone from `src/`.
- **Backoff and tracked downloads** (block 80): `BackoffState`, `BackoffPolicy`, `load_backoff_states`,
  `save_backoff_states`, `is_tracked`, `tracked_states`, `queued_target_id`, `DownloadCatalogReader`,
  `WaitingReason.LOCAL_PROCESSING`; local.db 0010 renames the `scheduler_state` key and the
  `waiting_reason` value.
- **Sources and the catalog columns** (block 90): `SourceUsefulness`, `carried_role_max_age`,
  `connectable`, `session_received_bytes`, `duration_seconds`; the alerts `FirstUseful` and `Reappeared`,
  events `SourceFirstUseful` and `SourceReappeared`, `source_alerts{kind="first_useful"}`, new titles and
  body; catalog 0012 holds only the three `RENAME COLUMN`s.
- **Observability** (block 100): `MetricOperation`, `notification_title`, `notification_body`,
  `_AlertTimer.observe`, the `*_AFTER_SECONDS` constants, `AppriseTargets`,
  `SearchExecuted.observation_count` and its log "observation(s)"; `crawler.yml`'s notification `tag`
  becomes `audience`, the old key refused by name.
- **Config parsing** (block 110): one `error_label` per parser, `section` for a sub-mapping, `document`
  for the root; a root key's error prints bare, without the `crawler.` prefix.
- **The crawler's other names** (block 120): `dedupe_keywords` and `SearchKeyword.origin` dropped (D8),
  `decide_download(size_bytes)`, `SearchTaskRunner`, `build_crawler_app`, `merge`'s `source_catalogs`,
  the amuleapi client's and mapper's names, Kad's `kad_word`, `register_sql_functions`.
- **The webui** (block 130): query keys `search`, `direction`, `target_id`, `source_name`, the 4.x ones
  ignored; `?done=restarted`; the nav reads "Node"; the composition's kept params, directions and
  context keys; the interval's names; `coverage_of` and `title_by_id` (D8).
- **The matcher** (block 140): `candidates` for `FileCandidate`s, `split_words`, `_RuleHit`,
  `evaluate_file`, `resolve_target`, `MatchingConfigError`, `TargetSegment.letter`,
  `FileCandidate.size_mib` and `duration_seconds`; `matcher.yml`'s `min_coverage`, `min_similarity`,
  `{letter}`, `size_mib`, `duration_seconds`, each 4.x key refused with its new name; `deploy/matcher.yml`
  and the golden corpus follow.
- **The other packages** (block 150): `p2pwatch_amule.config` becomes `p2pwatch_amule.boot`, the
  entrypoint, the bump's checklist and four documents with it; one `AMULE_CONF_PATH`; port-sync's
  `port_sync_settings`, `latest_restart_monotonic`, `now_monotonic`; `amule_bump`'s
  `build_pull_request_body`, `latest_release_tag`, `*_MAX_CHARACTERS`; `vex_guards`' `advisory_id`,
  `DpkgPackage`, `DpkgPackageAbsent`, `DpkgMinVersion`, `ProgramNeverInvoked`,
  `evaluate_source_guards`.
- **The holistic review's fixes** (block 160): `SourceReading.source_name` and
  `RecordedReading.source_name` from the mapper on, `EarlierPoints.latest_known_at`,
  `SourceReappeared.absent_for_seconds`; the source history tables head "Connectable"; "download
  enabled" for "full mode" and "observer mode"; the `merge` CLI says "source catalog" (`CATALOG`,
  `output_is_source_catalog`); the coverage token's refusal names its token; `docs/migration-4x.md`
  lists only what 4.1.0 shipped; "audience" for a notification destination in the French docs, with
  its glossary row.

## Decisions taken during Act

No block report records a class 2 question. The 🆕 on the first-useful title went to the operator
(holistic finding 7, below). Each block applied its concept at sites the inventory did
not list, named in its report; the ones a reviewer may weigh:

- Block 40: the port, adapter and their test modules renamed with `git mv`.
- Block 50: the tests' callable clocks became `FakeClock`; `tests/application/conftest.py`'s catalog runs
  on `AsyncioClock()`, since a frozen clock dedupes two observations at one instant.
- Block 60: `TargetTitle(target_id, title)` is a frozen dataclass in `events.py`.
- Block 70: the prose says "re-evaluation", the spelling the logs already used; the code word stays
  `reevaluat*`.
- Block 80: `download_policy(already_downloaded=)` became `already_tracked`; the cycle's "MONITOR" step
  and its log say "reconcile".
- Block 110: the removed and moved refusals print root keys bare too; `_required` is the one place a
  missing key is refused.
- Block 130: the kept params are qualified by what they keep (`filter_params`, `facet_kept_params`,
  `link_params`...).
- Block 140: `evaluate_file`'s filtered local is `matchable_candidates`; the `{segment}` refusal lives in
  `_check_regexes_compile`, so a fragment may now be named `segment`.
- Block 150: the test module `test_config_main.py` follows its module to `test_boot_main.py`;
  `AMULE_CONF_PATH` lives in `boot/conf.py`, which both entry points import; `GitHubRepo._name` became
  `_full_name`.
- Block 160: the CLI description "eMule crawler (observer)" loses its mode with the log and docstrings
  (finding 6); the `merge` CLI's two other messages and its log, and `docs/operate.md`'s merge section,
  say "catalog" with the two messages the finding named (finding 9).

## Class 1 fixes

- Block 20: a test renders the two reachable `{% else %}` branches of a source without a name.
- Block 30: `docs/migration-4x.md` never said the three search metrics gained a `client` label in the 5.0.
- Block 40: two comments in `test_record_observations.py` described a per-hash subject that does not
  exist.
- Block 50: `catalog_repository.py`'s docstring promised a long-done "plan C".
- Block 100: "clocks" for the alert timers and "channel" for a notification destination; a `# noqa`
  directive ruff called invalid.
- Block 130: `catalog_read.py`'s docstring named `coverage_for`.
- Long dashes in the docstrings and comments each block touched (blocks 30 to 80 and 100 to 140), the
  only class 1 fix of blocks 60, 70, 80, 110, 120 and 140.
- Block 160: `merge/__main__.py`'s docstring named the removed `tools/ec_probe.py`;
  `docs/operate.md`'s merge example quoted "expected 11", the schema being 12.
- Blocks 10, 90 and 150: none.

## Spec corrections

Every `(Corrected: ...)` in the spec: D6 (block 20 renamed each of the 209 attribute accesses one at a
time; three, in `{% else %}` branches, failed no test); block 30's `n_results` counts observations, so
block 100 renames it `observation_count`, and its debug log with it. The closing block adds four: D1
gains the `audience` row, so section 5 counts 23 glossary rows; D5 and section 6's migration page lists
only the surfaces 4.1.0 shipped; section 4's closing block passes the 20-file bound (39 files of
one-to-few-line fixes) under the one-line exemption, by the operator's ruling.

## Wrap counts

Counted with `gh run list --branch <b>` on each stack branch, 2026-10-14, before the closing block's own
run; each branch's pushed head (`git rev-parse origin/<b>`) is the head its one run tested.

- **Fix-backs**: 0. **Cascaded rebases**: 0. `origin/main` has not moved from `f9783b4`, so no rebase
  onto it yet.
- **Runs**: one per pull request, each green at its first head: #200 `38460679528`, #201 `38462695123`,
  #203 `38464304231`, #204 `38465380557`, #205 `38467038565`, #206 `38468289624`, #207 `38469608520`,
  #208 `38471200325`, #209 `38473300947`, #210 `38474368028`, #211 `38475500844`, #212 `38476653350`,
  #213 `38478458439`, #214 `38480585814`, #215 `38482050593`. Runs re-triggered: 0 against 16 blocks.
- **Bodies the operator called unreadable**: none known at writing.

## Holistic review

`.reviews/descriptive-names-holistic.md`, over `git diff origin/main...origin/refactor/package-names`
(head `ad0bc9c`): 0 critical, 0 major, 13 minor. Its own gate, `docs-build`, CI run `38482050593` and
section 5's string check were green. Each finding and its exit:

1. `docs/migration-4x.md` listed six renames of surfaces 4.1.0 never shipped (`waiting_reason`,
   `directly_reachable`, `transfer_counter`, `kind="new"`, the alerts' titles, `/sources`' keys): fixed,
   the page keeps only 4.1.0's, line 36 reflowed; D5 and section 6 corrected.
2. `docs/contributing/architecture.md`'s code map said `config/` for the boot step: fixed, `boot/`.
3. The French docs called an audience a "canal", their word for a client's channel: fixed, "l'audience"
   at the five sites, and the glossary gains `audience` (`AGENTS.md` and D1, identical).
4. "de nouveau utiles", "horloges" and the column "Groupe": fixed, the heading "Le seuil de l'alerte
   reappeared" (its anchor followed), "ces délais", "Utilité".
5. The source history tables headed `connectable` "High-ID": fixed, "Connectable".
6. "full mode" and "observer mode" for `download.enabled`: fixed, "download enabled" and "download off
   (crawl-only)" in the log, the comment and the docstrings.
7. The 🆕 on the first-useful title reads "NEW": asked of the operator.
8. `SourceReading.name` and `RecordedReading.name` for a source's name: fixed, `source_name`, the
   writer's SQL parameter with them; the column stays `name`.
9. The `merge` CLI said "source" for a catalog: fixed, `output_is_source_catalog`, the positional
   `CATALOG`, the help and the messages say "source catalog".
10. `EarlierPoints.last_known_at` and a local `last` without `first`: fixed, `latest_known_at`, `latest`.
11. `SourceReappeared.absent_seconds` off the `_for_seconds` pattern: fixed, `absent_for_seconds`.
12. The coverage token's refusal named no token: fixed, "token 'title_hit': key 'min' was renamed
    'min_coverage', rename it in matcher.yml", the doc's quote with it.
13. Diff hygiene: fixed, `catalog_repository.py`'s docstring reflowed, two long dashes replaced.

## Pitfalls

- **The 5.0 breaks every renamed surface 4.1.0 shipped**, each a step in `docs/migration-4x.md`: the
  start notification, the metrics' `network` label (now `channel`), `local.db`'s `backfill_state` and
  `channel_backoff`, the catalog's `media_length_sec` in SQL console queries, `/files`' query keys and
  `?done=restart` in bookmarks, and these config keys, refused at boot with their new name:
  `crawler.yml`'s notification `tag`, `matcher.yml`'s `min` and `fuzz` on a coverage token or reference,
  `{segment}`, `size_mb`, `duration_sec`. The lot's other renamed surfaces arrived after 4.1.0
  (`p2pwatch_channel_connected`, `kind="first_useful"`, `connectable`, `session_received_bytes`,
  `local_processing`, `/sources`' keys): a page for 4.x readers that names them describes renames they
  never met (holistic finding 1).
- **Serena's language server misses names it cannot see as one symbol**, each met in this lot and found
  by `git grep`:
  - a Protocol method's rename reaches neither its implementations nor a call through a variable
    annotated with the port and assigned a stub (blocks 40, 60, 70, 80): rename each implementation on
    its own, then grep the call sites;
  - keywords of `dataclasses.replace(obj, old_field=...)` (blocks 80, 90, 100), of a `match` class
    pattern (`case X(old_field=...)`, block 140), and a positional pattern's capture name (block 150);
  - a keyword read back by string from a captured `**kwargs` (block 130), names patched by string
    (`monkeypatch.setattr(module, "NAME", ...)`), docstrings, YAML, SQL, shell and Markdown;
  - comprehension variables are not symbols (`main/cve` not found in block 150): edited by hand;
  - a module is not a symbol: `git mv`, then the import lines, then `uv run poe fix` re-sorts them;
  - `replace_symbol_body` on a decorated class drops the decorator (block 120); `safe_delete_symbol` on a
    PEP 695 alias leaves `type  = ...` (block 50); renaming a method and its parameter in one parallel
    batch fails on the parameter (block 100);
  - `rename_symbol` reports "N changes applied" per file, not per site.
- **A test that writes through today's repository into a pinned older catalog breaks at each column
  rename**: the pre-rename shapes live in `older_catalog.py` (block 90).
- **A probe that rewrites templates must run alone in the tree**, since the gate reads the same files
  (block 20).
- **Starlette's `TestClient` warns when a test reads a response's context**: block 130's test wraps the
  app in an ASGI recorder requesting `http.response.debug` itself.
- **`caplog.messages[0]` depends on the suite's order**: in the full run, `open_catalog`'s "migration 1:
  applying" reaches the merge CLI test's capture first. Assert a message is in `caplog.messages`, not
  its position (block 160).
- **One file's hunks split between two commits** with `git diff -U0 <file>`, the hunks kept by a script,
  then `git apply --cached --unidiff-zero`, since `git add -p` is interactive (block 160).

## Left for the webui's read side

Section 2 kept the read side out; its lot inherits: `SearchBar.query`, `catalog_read.py`'s `query`,
`direction`, `target` keywords and `DEFAULT_DIR`, the name page's context key `name`, `TimelineRow.name`,
`CatalogReader._file_name`, the files view's sort value `name`, `ReevalRow`, the dead
`{% else %}{{ row.short_hash }}` at `sources.html:26`, and the source and name pages' "Next" link, which
no test renders. `BACKLOG.md`'s entry "The webui's read side" carries it, with the dead branch.

Kept outside the inventory and weighed by the holistic review as no finding: `CrawlerApp(client_factory=)`
beside `MuleClientFactory` (it builds a client, the glossary's port object).

## Validated by CI only

The integration suites were not run locally in this lot. CI ran them in `build-and-verify`, on amd64 and
arm64 (`Compose smoke stack integration`, then `API, download and orchestration integration`), green on
every pull request above. For block 150, the compose smoke is the only run of the aMule image's
entrypoint under `python -m p2pwatch_amule.boot`; locally, the module resolves and exits on its first
check (`PUID is required`) before any change.

## Not validated

- Migrations `local/0009`, `local/0010` and `catalog/0012` on the node's real databases; 0012 rewrites
  schema pages only (SQLite's documentation, the spec review's probe).
- The node's own config at the 5.0: its `matcher.yml` holds `min: 0.6` and `{segment}` (lines 34, 42),
  refused until step 3 of `docs/migration-4x.md` is applied; its `crawler.yml` was not read.
- A real apprise target configured with `audience:`.
- The weekly `amule-bump` run with its renamed functions; its tests run `main` end to end on a fake
  repository.
- Dashboards and alert rules on the renamed metrics: none ships in `deploy/`.

## Next

The operator reviews the stack, the lead rebases it onto `main`, and the operator merges. `BACKLOG.md`
no longer holds "Descriptive names"; "The webui's read side" carries the operator's direction of the
spec's section 7. The lot changes the image, but the next release
(the 5.0) still waits for the copy before a migration that rewrites rows (`BACKLOG.md`), as the previous
handoffs state.

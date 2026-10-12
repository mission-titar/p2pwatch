# Handoff: stage 4, source history and the `new-source` and `reappeared` notifications

Drafted by block 70, to be corrected by the closing block 80.

## State

Tier Spec lot, spec `agents/specs/2026-10-11-stage4-source-history.md` (approved 2026-10-12).
Fourteen blocks, one stack cut from `main` at `c7cd2c6`: #177 (10), #178 (15), #180 (17), #181
(20), #182 (25), #183 (30), #184 (35), #185 (40), #186 (50), #187 (60), #188 (65), #189 (67),
block 70 (`docs/stage4-docs`), then the closing block 80 (`docs/stage4-closing`). Two blocks split
over the 500-line bound during Act: 15 into 15 and 17, 65 into 65 and 67.

Nothing of the stack is merged and no release follows (spec section 2; stage 1's D16): the node
pulls `latest`, which stays on `mulewatch` 4.1.0. `git tag -l 'v*'` still ends at `v4.1.0`.
`catalog.db` goes to schema version 10 (`catalog/0010_source_history.sql`); `local.db` stays at 8.

From block 30 on, a node in download mode reads the sources of every download the crawler queued,
each round, and writes them as time ranges; from block 35 on, it notifies the community when a
source becomes useful for the first time or again.

## What was built

- **The model and the tables** (block 10): `domain/source.py` (`SourceKey`, its own uuid5
  namespace `https://mission-titar.github.io/p2pwatch/source`, `SourceRole`, `SourceReading`);
  `sources`, `source_variants`, `source_ranges` with D3's three indexes; append-only triggers on
  the first two; on `source_ranges`, a `DELETE` raises and an `UPDATE` passes only when the key is
  unchanged, nothing goes down and, if anything grows, no later range of the same
  `(variant_id, node_id)` exists; a no-op update passes. D17's `CHECK` rule is in
  `docs/contributing/architecture.md` §8.2.
- **A role's group and D9's reads** (block 15): `SourceGroup`, `carried_role`, `is_contact_point`
  (eD2k: IPv4 `ip:port`, port 1 to 65535); `earlier_ranges(source, started_before)` and
  `has_ranges_before(started_before)` on `SqliteSourceRepository`.
- **The writer** (block 17): `record_readings(file, readings, read_at, tolerance)`, one transaction
  per call, D4's three conditions, D3's carried group, the contact point checked against the file's
  network, returning `OpenedRange`s with their roles.
- **The amuleapi reading** (blocks 20, 25): `SourceClient.sources(file)`; keyset paging of
  `GET /downloads/{hash}/clients` on `ecid` (`_collect` takes one `identity` parameter);
  `source_ecid(row)` applies D1's filter before any detail call; one `GET /clients/{ecid}` per
  source, a `404` drops that row; `map_source(row, detail)`; `merge_duplicate_sources`. A new
  `ApiNotFoundError(ApiRejectedError)` is raised on amuleapi's `not_found` code.
- **The cycle's sources step** (block 30): last step of `run_download_cycle`, for each tracked,
  listed, non-completed download; tolerance `3 x poll_interval_seconds`. `DownloadDeps` gains
  `source_client`, `sources` and `poll_interval_seconds`; the composition's factory returns
  `DownloadSourceClient` (the intersection of both ports).
- **The notifications** (block 35): `application/source_alerts.py` (a pure decision), `SourceNew`
  and `SourceReappeared`, titles `🆕 New source` and `🔁 Source useful again`, audience community,
  counter `p2pwatch_source_alerts{network, kind}`; `download.reappeared_after_hours` (default 12)
  parsed into `reappeared_after: timedelta`. Every number of `crawler.yml` now refuses `.inf` and
  `.nan` at boot (class 2, below).
- **`merge`** (block 40): `sources` and `source_variants` copied with `INSERT OR IGNORE`, the
  variant remapped through `content_hash`; `source_ranges` upserted with `MAX` of each growing
  value, `ORDER BY first_seen_at`. `--help` reads "rows appended, source ranges united".
- **The webui** (blocks 50 to 67): the file page's "Source history" section; `/sources` with its
  search (`q`: a hash prefix, or a substring of any name the source carried) and a nav entry after
  "Files"; `/sources/{source_id}` (the full hash, its names, its ranges over every file);
  `/sources/name?name=` (the hashes that carried the name and the hash-less ranges under it, direct
  links only). `_FILE_ID` became `_HEX_ID`, shared by both detail routes.
- **Docs** (block 70): the invariant rewritten to umbrella D10's text in `AGENTS.md`, `README.md`,
  `docs/index.md`, `docs/contributing/architecture.md` (§1 and §11), `domain/observation.py`'s
  docstring and a comment of `webui/composition/app.py`; `docs/legal.md` (what a node records, no
  peer address, notifications, a shared catalog); `docs/operate.md` (a "Historique des sources"
  section with the roles and both alerts, the three routes, `merge`'s range union);
  `docs/settings.md` (`download.reappeared_after_hours`); `architecture.md` §8.3 (the three tables,
  the writer's rule, the trigger, the union); `AGENTS.md`'s WebUI and Persistence rows.

## Decisions taken during Act

- **Block 15 split** over the line bound (first measure 694 / 5), lead's decision: the writer
  became block 17, reusing commit `883e823`.
- **Block 20's question** (a spec gap: block 20 had no mapper while its acceptance needed
  readings), answered by the lead: the boundary moved along the call, block 20 maps the list row and
  block 25 the detail, the merge and the no-address criterion.
- **Class 2, block 30**: `sources()` and `downloads()` raise `ApiRejectedError` (a
  `DownloadRejectedError`) on `amuled_rejected`, which escaped the cycle and stopped the crawler;
  latent at the pinned commit. Operator: "Oui le corriger semble bien". The cycle now catches
  `ClientUnreachableError` and `DownloadRejectedError` together on both reads.
- **Class 2, block 35**: `_positive` accepted `.inf` and `.nan` for every number of `crawler.yml`.
  Operator: "Ok corrige. De toute façon ce sont des edge cases pas acceptés et que personne ne
  mettrait volontairement." `_number` now refuses a non-finite value, naming the key.
- **Block 65 split** over the line bound (544 lines, 7 files), lead's decision: the name page became
  block 67 (`c7c9094`).
- **Block 10**: `source_ranges`' `DELETE` trigger raises the update's message;
  `SourceReading.raw_meta` is a tuple of pairs, like `FileObservation.raw_meta`.
- **Block 15**: `earlier_ranges` takes the `SourceKey`; `contact_point`'s check lives in the domain
  (`is_contact_point`), called by the writer.
- **Block 20**: `sources` on a file of another network answers `()` without a request; the list's
  `404` is told by the `not_found` code, not the status.
- **Block 25**: `directly_reachable` is also unknown when `ed2k_user_id` is absent or `high_id` is
  not a boolean; merged readings keep the higher-ranked reading's fields with the larger counter,
  ties to the first row in `ecid` order.
- **Block 30**: a `RepositoryError` writing one download's readings skips that download only;
  `poll_interval_seconds` moved to `DownloadDeps`; an unreachable daemon at `_start_unlisted` ends
  the round before the sources step.
- **Block 35**: `earlier_ranges` is asked for every opened range with a user hash, the role check
  stays in the pure decision; a `RepositoryError` from `has_ranges_before` skips the step, one from
  `earlier_ranges` that download's remaining alerts.
- **Block 50**: times read `2026-10-13 20:00:30Z` (seconds kept), not "At a glance"'s
  `Tue 20:00:00`; "unknown" for a missing value; Received and Rate blank outside `sending`.
- **Block 60**: "latest name" is the latest named range's; ties on last seen order by `source_id`.
- **Block 65**: the source page shows the full hash; one `page` parameter moves both tables; an
  unknown well-formed id answers 404.
- **Block 67**: a hash row's "Last seen" and "Files" count its ranges under this name only.
- **Block 70**: `docs/operate.md` had no community list to extend; the two alerts got a section of
  their own, "Historique des sources", and their titles joined the embed colours' paragraph. Class 1:
  `operate.md`'s merge example read `expected 9`, now `expected 10`. Beyond D15's list:
  `architecture.md` §7 points at the sources step and §12 names `ports/source_client.py`.

## Spec corrections

For the closing block to check against the spec and apply, each with a `(Corrected: ...)` marker:

- "Transient states inside the stack", "Blocks 30 to 65: sources are recorded and readable only
  through the SQL console": the webui reads them from block 50 on (block 67's report).
- D8, "a `RepositoryError` skips this step": per download for a write (block 30).
- D9, `download.reappeared_after_hours`: carried as a `timedelta`; every key now refuses `.inf` and
  `.nan`, not only this one (block 35).
- D12 against "At a glance": the time format (block 50).
- Section 6, "The webui": the source page shows the full hash, not a shortened one (block 65).
- D13: a name page's hash rows count only the ranges under that name (block 67); `/sources`' `q`
  matches any name ever carried (block 60).
- D15: `docs/operate.md`'s "community list" does not exist (block 70).

## Wrap counts

Draft, to be re-counted by the closing block after its own runs; command, per stack branch:
`gh run list --branch <b> --workflow pr.yml --json headSha,event,conclusion,createdAt`.

- **Fix-backs during Act**: none forwarded by the lead as of block 70. Blocks 30 and 35 each pushed
  a class 2 fix after their first push.
- **Cascaded rebases**: none known to block 70; the lead counts them.
- **Runs, for 12 pull requests (#177 to #189)**: 18. One per branch, plus `feat/record-sources` 2
  (`5675a67` cancelled, `421e893`), `feat/source-alerts` 2 (`c344b8f`, `0c0ddbd`),
  `feat/webui-source-pages` 2 (`2da4f0a`, `d942c0d`), `feat/webui-name-page` 4 (`4ab1be5` and one
  `c7c9094` cancelled, `c7c9094`, `cdbd356`). Re-triggered: 6. Block 70's and 80's runs not counted.
- **Bodies the operator called unreadable**: to be filled after the operator's review.

## Holistic review

Pending: run at the head of Wrap over `git diff origin/main...origin/docs/stage4-docs`.

## Pitfalls

- **A test that opens the latest catalog to exercise one migration breaks when a later one lands**:
  pin it with `open_catalog_at(path, N)`.
- **A seeded fixture with a lower counter opens a second range for that reason alone**, masking the
  condition a case means to test: mutate each parametrized case's own condition.
- **A reading without a user hash must match only variants without one**: by name alone it extends
  a hashed source's range.
- **A mutation script that replaces a line from its first non-blank character mis-indents the
  next**: the suite fails to collect, which a count of `FAILED` lines reads as a surviving mutant.
- **`role`, `download_state` and `a4af` come from JSON**: test membership against a tuple and type
  the state before a dict lookup. `download_state` is the client's, copied on each of its rows, so on
  an A4AF row it describes the other file.
- **`role` and `a4af` exist only on the per-file list row**, never on `GET /clients/{ecid}`: the row
  decides first.
- **`server_port` can be 0 while `server_ip` is known**: not a contact point.
- **The adapter's `ApiRejectedError` is a `DownloadRejectedError` and a `SearchFailedError` at
  once**: on a read, a refusal arrives under the download port's name.
- **A `match` without a wildcard arm leaves an uncovered arc** under `branch=true`; an `isinstance`
  expression avoids the `assert_never` pragma.
- **Rows holding BLOBs sort differently** under `rows_without_id`'s text sort and Python's natural
  sort: sort both sides with one key.
- **The webui's template guard forbids `{% if %}`**: an optional link is a 0-or-1 tuple rendered
  with `{% for %}`/`{% else %}`.
- **A block split takes its tests with it**: a shared behaviour may lose its only test; rerun the
  mutations on each half.
- **A rewritten hunk counts its deleted lines** in the block's budget.
- **A route shadowed by a parameterised sibling answers the expected 404 before it exists**: a 404
  test there proves nothing until a mutation makes it fail.
- **`uv run poe docs-build` fails on a dead anchor**: a link to `operate.md#historique-des-sourcez`
  aborted it (`Aborted because --strict flag is set`), checked in block 70.

## Not validated

- **Section 4's measure on the node**: once the node runs this stack (no release is planned, so on
  the operator's decision, through the `main` image), after one hour, each (file, source) pair under
  2 ranges opened without a change of role:

  ```sql
  SELECT v.file_id, v.source_id, v.name, COUNT(*) AS opened
  FROM source_ranges AS r JOIN source_variants AS v USING (variant_id)
  WHERE r.first_seen_at >= :since
  GROUP BY v.file_id, v.source_id, v.name, v.role
  ORDER BY opened DESC;
  ```

  The result goes to the handoff of the lot during which the node first runs it.
- **Against a real amuled**: no `api_integration` test reads sources; the fake follows
  `REFERENCE.md` and `src/webapi/Api.cpp` at the pinned commit.
- **The sources step's cost inside the cycle**: sequential detail calls, about 73 per 30 s round
  at the node's size (D8); D4's tolerance assumes the cycle stays under half a poll.
- **A notification on a real apprise target**: the texts are asserted on `describe` only.
- **The webui pages in a browser, and their timing on the node's catalog**: `/sources` aggregates
  every range per request; the source page reads `best_name` per file, at most 50 per page.
- **`has_ranges_before` after a `merge --into`** of other nodes' ranges: no index leads with
  `node_id`, so a miss is a full scan, once per round.
- **A `merge` of real node catalogs holding source ranges**: none exists yet.

## Next

The operator reviews the stack, the lead rebases it onto `main`, and the operator merges. **No
release is proposed** (stage 1's D16: none before the first new network). `BACKLOG.md`'s "Stage 4"
entry is deleted by the closing block; stage 5 stays open, with D2's table of identities to verify
per client. Once the node runs this stack, section 4's count above.

# Handoff: the node id no longer set in crawler.yml

## State

Tier Direct, one branch `refactor/drop-configured-node-id` cut from `main` at `903c7864`, one pull request. It changes
what the image runs (the config parser and the node id's resolution), so a release may follow it, after "A copy before
a migration that rewrites rows".

The session opened the backlog entry "The node page shows a node id set in `crawler.yml`". The key was documented
nowhere (`docs/settings.md`, `deploy/crawler.yml`) and no suite set it; the operator confirmed that neither they nor the
researchers working with them ever set it. The fix the spec weighed (show the resolved id, or the recorded one) gave
way to removing the key.

## What was built

- **`node_id` joins `_REMOVED_KEYS`**: `crawler.yml` refuses it by name, `CrawlerConfig` loses the field and
  `NodeIdResolver` its `configured_node_id`, so the id is always the one `local.db` holds and `/node` shows it.
- **The composition's wiring tests record their node id in `local.db`** before the run, as a node started before.
- **`FakeNodeIdStore` loses its `reads` counter**, whose only reader was the removed test.
- **`docs/migration-4x.md` names the refusal**; the backlog entry is deleted.

## Evidence

- Red before the parser change: `test_a_removed_key_is_refused_by_name[node_id]` failed with
  `'non-empty string or absent expected, got 5.0' != 'was removed, delete it from crawler.yml'`.
- `uv run poe check` exit 0 at the branch's tip (crawler `1633 passed, 15 deselected`).

## Decisions

- **Tier Direct**, by the operator: removing a key nobody set and nobody documented is no change to a surface an
  operator uses, and Spec would be ceremony.
- **Removal over either fix**: recording a configured id clashes with `record_node_id`, which refuses a second one;
  showing the resolved id needs a port and an in-memory store for the webui, for a setting no one uses.

- Continuous integration green on the pull request (#511, run 40407750387, `success`), merged as `803ab181`.

## Next

The backlog, "A copy before a migration that rewrites rows"
first.

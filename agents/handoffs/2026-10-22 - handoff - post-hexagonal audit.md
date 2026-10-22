# Handoff: the post-hexagonal audit and the docs that follow the tree

## State

The hexagonal umbrella is finished: lots 1a, 1b, 2, 3a, 3b and 3c are merged (`main` at `1d677b82`). Nothing is
released since; a release still waits for the backlog's "A copy before a migration that rewrites rows".

After it, on 2026-10-21 and 2026-10-22, the lead ran an audit of the inconsistencies left: four Opus agents (the
crawler hexagon's architecture, naming across the eight packages, the five other hexagons, the guidance and docs
against the tree) and one Sonnet agent (the hexagonal literature), then a Discuss with the operator that arbitrated
every finding. The ledger, one row per finding with its decision and exit, is
`agents/reference/2026-10-22-post-hexagonal-audit.md`: 0 rows left open.

This tier Direct lot (branch `docs/docs-follow-the-tree`, one pull request) fixes the ledger's D rows: the docs and
guidance that no longer said what the tree does. Everything else the ledger decided is code, for the lots below.

## What was built

- The daily Grype scan described as it runs: v4's single `mulewatch` image until v5 ships, then one leg per image
  (`AGENTS.md`, `SECURITY.md`, `docs/contributing/testing.md`, `docs/verify-image.md`).
- `AGENTS.md`: the single-test example's path (`tests/domain/test_engine.py`); the integration suites never run by
  the local gate but run by CI's required check; `_unit-coverage-check`'s name.
- `docs/contributing/testing.md`: only the crawler's `addopts` has integration markers; `release.yml` calls
  `validate.yml` on every push to `main` too; the stale "other packages' sections".
- `docs/operate.md`: boot reconciles `amule.conf` on every start (the EC password and `[AmuleApi]`); the two
  database paths are required keys, not defaults. `docs/settings.md` and `docs/contributing/architecture.md`: the
  download and the metrics are on in the shipped `crawler.yml`, off without their section.
- `docs/limits.md`: `no-new-privileges` with the privilege drop is checked by the smoke stack in CI.
- `packages/matching/AGENTS.md`, `BACKLOG.md`'s time-zone entry, `ports-imports.yml` (`enum`, which no port imports,
  off the list), `code-pattern-check`'s help.

## Decisions taken in the audit's Discuss

Each with its evidence and exit in the ledger. The rules, which the next lots apply and `AGENTS.md` will state:

- The composition implements the driving port that runs its assembled graph (`CrawlerRunner`, `PortSyncLoopRunner`),
  stated as a rule; `CrawlerApp` and `PortSyncApp` become `CrawlerComposition` and `PortSyncComposition`; every
  hexagon's whole composition moves to `composition/`, `__main__.py` only reading argv, env and cwd (tach-checked).
- `application/` holds `ports/{driving,driven}/` (the ports leave their own ring, as the common usage has it),
  `use_cases/` (called from outside through a driving port), `steps/` (called only from inside) and at most one
  `<x>_lifecycle.py` (`RunCrawler` becomes `CrawlerLifecycle`, `RunPortSyncLoop` `PortSyncLifecycle`); code that
  calls no port goes to `domain/`.
- One port per file, named after it; one driving port per use case confirmed.
- A stored-state adapter is `<System><Thing>Store` ("store" in the glossary, `RepositoryError` to `StoreError`);
  an adapter's name is the system, the thing and the role; the system is what would need another adapter if
  replaced, never a syntax (`Json`, `Yaml`).
- `Reader`/`Writer` only over our own state; an outside system keeps a capability name. A Writer returns nothing;
  `record_*` adds a fact, `set_*` replaces a value.
- A check returns a report (`validate-config` included); a problem is a typed value the command line formats; a
  broken input raises.
- Logger names derived from the code (`__module__`, `__name__`); a value the operator could set and did not is the
  domain's; a fixed value is the composition's.
- A domain object carries the node that produced it, as it carries its instant; `node_id` stays a parameter only as
  a read's filter.
- Fakes: one per port, at the mirror of its port's file under each package's `tests/fakes/`; `p2pwatch_testing`
  folds into the crawler's `tests/`; each package gets its `[tool.pyrefly]` and `pyrefly check` (import errors)
  joins the gate. pytest's shared settings come from an auto-loaded workspace plugin.
- The operator's order for any fix: enforced by design, else by tests, else by a gate tool, a convention last.

## Pitfalls

- **pyrefly resolves `tests.*` only with a per-package config** (trial on a scratch clone at `1d677b82`):
  `[tool.pyrefly]` with `python-interpreter-path = "../../.venv/bin/python"` and `search-path = ["src", "."]`, in this
  order; `"."` alone collapses a rename to one site, and without the interpreter path the LSP takes Serena's
  `pythonPath` and loses src sites. Its sub-configs cannot change import paths, so the section is per package.
  Today a rename from a port misses a fake's override defined in a `tests` module another test module imports
  (`RepoReader.read_file` 9 of 12 sites, `VexReader.read_claims` 8 of 11).
- `amule_bump`'s `test_bump_amule.py:97` carries a `missing-attribute` pyrefly reports, to fix before `pyrefly check`
  joins the gate.

## Not validated

- The pytest plugin's auto-loading through its `pytest11` entry point in the shared venv: to prove with a hand-run
  `pytest` in each package refusing a misspelled marker.
- The poe-free single-test command once the plugin lands (`AGENTS.md`'s example stays a plain `pytest`).

## Next

- The operator reviews and merges this pull request.
- The lead writes the tier Spec lot (likely several lots) from the ledger, its new names arbitrated one by one in its
  Discuss; the ledger stays the checklist until that spec holds every row.
- Then "Contract tests for the fakes", which the fakes' new layout prepares.

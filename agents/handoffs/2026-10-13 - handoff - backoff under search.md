# Handoff: the backoff under search

## State

Tier Direct lot, one branch `feat/backoff-under-search` cut from `main` at `e7e5c93`, one pull request.
Nothing of it is merged at writing. `git tag -l 'v*'` still ends at `v4.1.0`; neither database's schema
changes.

## What was built

- **`backoff` moves under `search`** in `crawler.yml`: `search.backoff`, parsed by `_parse_backoff` with
  the same bounds as before, into `SearchConfig.backoff`. `CrawlerConfig.search: SearchConfig` replaces
  `backoff` and `search_keywords`, the section's shape in the YAML.
- **A root `backoff` refuses to boot** with its new place: `crawler: key 'backoff' moved to
  'search.backoff', move it in crawler.yml` (`_MOVED_KEYS`, beside `_REMOVED_KEYS`).
- **`search.keywords` is required**: its code default `("keroro", "titar")` is gone. A missing `search`
  section reads `search: key 'keywords' missing`.
- **Documents**: `docs/settings.md` (the bounds table), `docs/migration-4x.md` (step 3 moves the section),
  `docs/contributing/architecture.md` §5 (the keywords without a default). `BACKLOG.md` loses the entry.

## Decisions

- **Tier Direct**, the operator's decision against the workflow's trigger (a config key changes): the
  target is forced by the code, `search` being the only search config, and the refusal follows
  `_REMOVED_KEYS`. Operator: "Est-ce que sémantiquement une spec a du sens ici ?", then "Lance."
- **Now rather than with stage 5**: the 5.0 already makes the operator edit `crawler.yml`, so the move
  joins that step instead of a second break. Stage 5 moves it again only if its clients need distinct
  backoffs.
- **Class 2, the keywords' code default**, against the multi-network spec's section 5 ("No keyword lives
  anywhere but in config, not in a patch and not in a code default"). Operator: "corrige, c'est une
  bonne suggestion."

## Class 1 fixes

- `test_search_keywords_rejects_empty_list` and `_non_string_entry` matched any `ConfigError`, so they
  passed on an unrelated error; each matches its message now.
- `_minimal_raw`'s docstring: a long dash, and "EC password" for the amuleapi one.

## Evidence

- `uv run poe check`: exit 0, every package at 100 %, no warning; `uv run poe docs-build`: "No issues
  found".
- Budget: 202 lines, 12 files, against `main`.
- Watched failing first: the root `backoff` (`Failed: DID NOT RAISE ConfigError`), a missing
  `search.backoff` (`Actual message: "backoff: key 'factor' missing"`), a missing `search` section and
  missing keywords (`Expected regex: "search: key 'keywords' missing"`). With the keywords' default put
  back, both keyword tests fail again (`DID NOT RAISE ConfigError`, then `Actual message:
  "search.backoff: key 'factor' missing"`).
- `deploy/crawler.yml` and `tests/smoke/crawler.yml` parse; `main`'s `deploy/crawler.yml` is refused with
  the message above.

## Pitfalls

- **A node whose `crawler.yml` keeps `backoff` at the root refuses to boot**, like one keeping
  `decision_poll_interval_seconds`: the 5.0 release notes must say to move it (`migration-4x.md`,
  step 3).
- **Serena's `find_referencing_symbols` returns no reference from a test file** in this repository
  (checked on `SearchConfig`, imported by three tests; the cause was not looked for): test usages still
  need a text search.

## Validated by CI only

The compose smoke reads the moved section of `tests/smoke/crawler.yml`, and `test_crawler_loop.py`
builds the new `SearchConfig`: both run in CI's integration jobs, not locally.

## Next

The operator reviews and merges. The lot changes the image, but the next release still waits for the
copy before a migration that rewrites rows (`BACKLOG.md`), as the previous handoff states.

---
paths:
  - "deploy/**"
  - "packages/crawler/src/p2pwatch/adapters/driven/config/**"
  - "packages/crawler/tests/domain/matching/**"
---

# Deployment config

- **Two run modes, one topology:** `download.enabled: true` (the shipped default) wires the download loop live; `download.enabled: false` or an absent `download:` section is crawl-only. This is a **config flag**, not two ways of assembling the stack: both compose variants start every service unconditionally, and there is no compose profile anywhere.
- **`deploy/` is the operator-owned single source of truth for config**: `deploy/crawler.yml` / `deploy/matcher.yml` / `deploy/targets.yml` stay editable-by-operator deployment config, next to the compose files that mount them; it is **forbidden to canonicalize them as code artifacts** (package data, inline policy dicts, or duplicate test fixtures that shadow them). Every consumer *derives from* `deploy/`, never the reverse: the matcher policy has exactly ONE copy (`deploy/matcher.yml`), read by the matching golden corpus + engine unit tests via `parents[N]`: a test-time path coupling to `deploy/`, deliberately accepted (test-only, not an import; the code DAG is unchanged). Do not reintroduce a `canonical_config.yaml` fixture or an inline `_CANONICAL_RAW` policy dict.

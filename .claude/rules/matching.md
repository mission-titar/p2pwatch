---
paths:
  - "packages/matching/**"
  - "deploy/matcher.yml"
  - "deploy/targets.yml"
---

# Architecture: the matching engine

The core is one layered, declarative matching engine under `packages/matching/src/catalog_matching/domain/`. **The matcher/rule policy is 100% in YAML config; the code is a minimal fixed engine.**

```
load_yaml(path)                         # the crawler's adapters/driven/config/yaml_loader.py: the ONLY I/O
  → parse_matcher_config / parse_targets   # validation.py: schema + fail-fast graph validation:
  →                                        #   DAG/named-cycle, depth bound (32), regex compile-check,
  →                                        #   unique target_id, closed tier/attr enums,
  →                                        #   no control character (Cc) in a segment letter or a
  →                                        #   rule name → MatchingConfigError
  → MatchingEngine(config, targets=..., max_filename_length=...)  # engine.py: one matcher tree PER TARGET
  → engine.evaluate_file(candidates)       #   one FileCandidate per filename of a file;
  →                                        #   brute-force over all targets (no funnel)
       → [MatchDecision(target_id=..., rule_name=..., tier=..., explanation=...), ...]  |  []  (file discarded)
```

Invariants: the decision is order-independent (target_ids are unique); `MatchDecision`'s `target_id`, `rule_name` and `tier` (a `DecisionTier`) are exactly columns of the crawler's `match_decisions` (persistence columns like `decided_at`/`node_id` are the crawler's, which adds them when it records a decision). Regex tokens compile under stdlib `re` with `re.ASCII` (was RE2 until 2026-07-03).

## Gotchas

- Regex tokens compile with `re.compile(pattern, re.ASCII)` (`matchers.py`, `validation.py`). `re.ASCII` keeps `\b \d \s \w` ASCII: matching the pre-2026-07-03 RE2 default the existing policy relies on (`fold()` does not reduce non-Latin scripts to ASCII). Case-insensitivity is a leading `(?i)` prefix (not a flag arg). An invalid pattern raises **`re.error`** (caught in `validation.py` → `MatchingConfigError` "not compilable").
- Don't validate config order-dependently (parse pass = structural; graph pass = full table). Recursive validators need an explicit depth guard → a clean `DepthExceededError`, not `RecursionError` (which is a Python runtime artifact, not a domain error).
- `golden_targets.yaml` is shared by this package's golden corpus and the crawler's `tests/application/conftest.py`: a change to it can break the crawler's tests too, so run both packages' suites.

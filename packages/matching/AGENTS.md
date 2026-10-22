# Architecture: the matching engine

The core is one layered, declarative matching engine under `src/catalog_matching/domain/`. **The matcher/rule policy is 100% in YAML config; the code is a minimal fixed engine.**

```
load_yaml(path)                         # the crawler's adapters/driven/config/yaml_loader.py: the ONLY I/O
  → parse_matcher_config / parse_targets   # validation.py: schema + fail-fast graph validation:
  →                                        #   DAG/named-cycle, depth bound (32), regex compile-check,
  →                                        #   unique target_id, closed tier/attr enums → MatchingConfigError
  → MatchingEngine(config, targets)        # engine.py: pre-resolves a matcher tree PER TARGET once
  → engine.evaluate_file(candidates)       #   one FileCandidate per filename of a file;
  →                                        #   brute-force over all targets (no funnel)
       → [MatchDecision(target_id, rule_name, tier, explanation), ...]  |  []  (file discarded)
```

Invariants: the decision is order-independent (target_ids are unique); `MatchDecision`'s three string fields are exactly columns of the crawler's `match_decisions` (persistence columns like `decided_at`/`node_id` are the crawler's, which adds them when it records a decision). Regex tokens compile under stdlib `re` with `re.ASCII` (was RE2 until 2026-07-03: see the root `AGENTS.md`'s Gotchas).

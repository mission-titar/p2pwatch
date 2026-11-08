---
paths:
  - "packages/crawler/src/p2pwatch/domain/matching/**"
  - "packages/crawler/tests/domain/matching/**"
  - "deploy/matcher.yml"
  - "deploy/targets.yml"
---

# Architecture: the matching engine

The core is one layered, declarative matching engine under `packages/crawler/src/p2pwatch/domain/matching/`. **The matcher/rule policy is 100% in YAML config; the code is a minimal fixed engine.**

```
load_yaml(path)                         # the crawler's adapters/driven/config/yaml_loader.py: the ONLY I/O
  → matcher_config_from_document           # the config adapter's matcher_config_schema.py (pydantic):
  →                                        #   fragments, tokens, conditions and rules (closed tier and
  →                                        #   scope, no control character (Cc) in a rule name), every
  →                                        #   problem listed, then validation.py: fragment_problems,
  →                                        #   then cross_value_problems: every unknown reference,
  →                                        #   veto, override, cycle, depth bound (32), regex
  → targets_from_document                  # the config adapter's targets_schema.py (pydantic): every
  →                                        #   problem listed, unique target_id by duplicate_targets
  → MatchingEngine(config, targets=..., max_filename_length=...)  # engine.py: one matcher tree PER TARGET
  → engine.evaluate_file(candidates)       #   one FileCandidate per filename of a file;
  →                                        #   brute-force over all targets (no funnel)
       → [MatchDecision(target_id=..., rule_name=..., tier=..., explanation=...), ...]  |  []  (file discarded)
```

Invariants: the decision is order-independent (target_ids are unique); `MatchDecision`'s `target_id`, `rule_name` and `tier` (a `DecisionTier`) are exactly columns of the crawler's `match_decisions` (persistence columns like `decided_at`/`node_id` are the crawler's, which adds them when it records a decision). Regex tokens compile under stdlib `re` with `re.ASCII` (was RE2 until 2026-07-03).

## Gotchas

- Regex tokens compile with `re.compile(pattern, re.ASCII)` (`matchers.py`, `validation.py`). `re.ASCII` keeps `\b \d \s \w` ASCII: matching the pre-2026-07-03 RE2 default the existing policy relies on (`fold()` does not reduce non-Latin scripts to ASCII). Case-insensitivity is a leading `(?i)` prefix (not a flag arg). An invalid pattern raises **`re.error`** (caught in `validation.py`: "does not compile as a regex").
- Don't validate config order-dependently (parse pass = structural; graph pass = full table). The token graph is walked with an explicit stack: a chain past the interpreter's recursion limit is a depth problem, never a `RecursionError`. The depth is checked only when no cycle was found.
- `golden_targets.yaml` is shared by this package's golden corpus and the crawler's `tests/application/conftest.py`: a change to it can break the crawler's tests too, so run both packages' suites.

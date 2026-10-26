# Handoff: the code-pattern rules in one directory

## State

Tier Direct, one branch `chore/ast-grep-one-directory` cut from `main` at `8cdcdbb4`, one pull request. It ships
nothing the image runs (gate configuration and documents), so no release follows it.

The session opened the backlog entry "The ast-grep rule tests bound to their rules by design" in Discuss. The operator
dropped it: the gain is too small for the cost of the only fix that binds them, and the entry is deleted. The
discussion then moved to where the rules live.

## What was built

- **`ast-grep-rules/`, `ast-grep-tests/` and `ast-grep-utils/` move to `ast-grep/{rules,tests,utils}`**, the root
  keeping `sgconfig.yml`, so a bare `ast-grep scan` and an editor's ast-grep extension still find the config.
  `vex_checks`' `sgconfig.yml` reaches the shared utilities at their new path; `AGENTS.md` names the new paths.
- **The backlog entry is deleted.**

## Evidence

- Probes on copies of the rules, ast-grep 0.50.0: a test whose rule id is renamed prints `Configuration not found!`
  and the run ends `13 passed; 0 failed`, exit 0; a rule whose test file is deleted runs no test and nothing reports
  it. The defect is upstream issue ast-grep/ast-grep#2994, open since 2026-10-09 and not fixed in 0.51.0.
- History since the rules' first commit (2026-10-15): no rule or test file renamed or deleted, no `id:` changed; one
  rule without a test for ten days (`no-dynamic-attribute`, 2026-10-15 to 2026-10-25), found by a review.
- After the move, a throwaway module in a crawler domain (`import imaplib`, `import socket`, a `Protocol` base) made
  `ast-grep scan` report `domain-imports` and `no-protocol-base`, and `vex_checks`' scan report `CVE-2025-15366`: the
  rules and the shared utility still fire. `poe code-pattern-check` `14 passed; 0 failed`, `poe vex-source-claims`
  exit 0.
- `uv run poe check` exit 0 at the branch's tip (crawler `1634 passed`).

## Decisions

- **No runner of our own**: ast-grep reads every `.yml` under `ruleDirs` as a rule, so a test file beside its rule
  breaks the scan (`missing field language`); binding them would take examples under the rule's `metadata:` and a
  runner in a hexagon of its own, which must also inline the shared utilities (`scan --rule --stdin` loads no
  `utilDirs`). The operator judged that cost above a defect that never struck.
- **`sgconfig.yml` stays at the root**: the root loses two directories, and the tool's discovery keeps working.

## Pitfalls

- A rule's `files:` globs resolve from where the scan runs, not from its `sgconfig.yml`'s directory, despite the
  docs: `vex_checks`' config, scanned from the root with `--config`, matches `packages/*/src/**`.

## Not validated

- Continuous integration at writing.

## Next

The operator reviews and merges the pull request. Then the backlog, "A copy before a migration that rewrites rows"
first.

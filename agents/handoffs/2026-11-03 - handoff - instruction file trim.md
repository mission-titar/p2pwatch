# Handoff: instruction file trim (tier Direct)

## Current state

`AGENTS.md` is now `.claude/CLAUDE.md` (the operator's choice: what is specific to Claude Code lives in `.claude/`), cut
from 62 KB to 35 KB. What concerns one part of the tree moved to path-scoped rules in `.claude/rules/` (glossary,
amuleapi, matching, SQLite persistence, coverage idioms, Serena), which Claude Code loads when its Read, Edit or Write
tool touches a matching path. The codebase overview, the gate sub-task detail and the emphatic wording were cut, on
Anthropic's guidance (under 200 lines, nothing the model can derive from the code) and on arXiv 2602.11988 (ETH, ICLR
2026: a codebase overview does not help agents; tooling and non-standard conventions do).

## Pitfalls learned

- **Serena's tools trigger no path-scoped rule.** Tested: a session that read and edited `AmuleApiClient` through Serena
  alone received none of the rules; the same read through Read loads them. `.claude/CLAUDE.md` lists each rule file with
  its paths and tells an agent working through Serena alone to Read the file first.
- **A subagent in a worktree takes the main session's instruction files**, not its worktree's (Claude Code docs,
  worktrees). To test a variant of an instruction file, run a separate `claude -p` session from the variant's directory,
  and put a canary instruction in the variant to prove it was read.
- An `@` import saves no context: the imported file loads at start with the file that imports it.

## Measured

One run of a mid-sized task ("Prometheus counts failed downloads, by reason") with the full file, as `claude -p`: Sonnet
7.5 min, Opus 9 min, Opus about 2.5 times Sonnet's cost; about 1.2 and 2.8 points of the operator's 5-hour plan window,
under one point of the week each. Both passed `poe check`. Context re-read on every turn dominates the cost.

## Not validated

Whether agents working through Serena follow the index and Read the rule file first. If they do not, a hook adding the
rule after a Serena call is the next step.

## Next step

The measurement agreed with the operator, for the Hard rules and the Naming section left in place: micro-tasks modelled
on the frequent kinds of change, the gate-checked rules removed by halves (group testing guided by priors), Sonnet only
during the search and Opus on the final file, the budget estimated and approved before any launch. The rules no gate
checks (naming, design) stay out until a judge is designed.

# Handoff: measured instruction trim (tier Direct)

## Current state

`.claude/CLAUDE.md` is cut from 35 KB to 10 KB on measurement: what stays changed an agent's result, what left did
not, or the gate catches it within a few turns. The design invariants that concern one subsystem moved to seven new
path-scoped rules (`amule-container`, `deploy`, `docs`, `merge`, `packaging`, `stores`, `text-encoding`); two stay in the
default context (no peer address in the catalog, no read of downloaded bytes). `coverage.md` is deleted.

## Method

Five micro-tasks written as operator needs, without naming a mechanism: A, pause history on the node page (a new store);
B, quiet hours in `crawler.yml`; C, a CSV export command; D, amuled's version in the boot log; E, an `extends-base`
template check, held out until the final run. Each ran as `claude -p` from a scratch worktree carrying the arm's
instruction files, a canary line proving they were read, hooks off (`--settings '{"disableAllHooks": true}'`). The agent
stopped once the package's tests passed; the gate then ran check by check, each violation labelled by its rule; a Sonnet
judge, run from a neutral directory, read the patch against the rules no gate checks (design, naming, glossary); then
the session was resumed (`--resume`) until `uv run poe check` passed, counting the fix turns.

## Measured

Sonnet, 8 runs per arm (A to D twice), cost to green from the CLI:

| | Cut to the floor (8.4 KB) | Full file (35 KB) |
|---|---|---|
| Cost to green | 16.50 $ | 16.38 $ |
| Fix turns | 205 | 153 |
| Runs with a judged violation | 6 of 8 | 4 of 8 |

- Kept: the rings and `tach.toml` (5 of 8 runs without them, 11 to 29 fix turns each; 2 of 8 with them), contracts (no
  gate sees a missing one: without the rule task A built a single `CrawlControlRecorder` and no contract; with it, a
  Writer/Reader pair and its store contract), one prohibition line each for patching, the clock and the core's imports
  (1 of 8 runs without, 0 with), and the naming bullets broken only without them (Reader/Writer, adapter names,
  `latest`, abbreviations).
- Cut: keyword-only, ruff and mypy, coverage by own tests (as often broken with the rule as without, a few fix turns),
  and the units no run broke in either arm (dynamic attributes, option defaults, dead code, one port per file, doubles,
  logger names, Reader/Writer verbs); `ON CONFLICT` was never exercised and goes on priors.
- Opus on the final file, one run per task, A to E: all green, no tach violation, no judged violation, contracts
  written for the ports over our own state, 5 to 25 fix turns on what the gate catches.
- Plan usage: 8 Sonnet runs and their judges took about 10 points of the 5-hour window and 1 point of the week.

## Pitfalls learned

- **The scratchpad lives in `/tmp`, which a reboot empties**: the harness and the raw outputs were lost once mid-run.
- **A resumed session rebuilds its cache**: on Opus the fix loop cost about as much as the task.
- **The judge misses some violations**: it passed a misnamed Reader/Writer port in one run and caught it in another.
- **A rule rewritten after the results can leak an answer**: a first draft of the adapter naming bullet listed `Csv`,
  the very name the judge had flagged on task C; it was removed before the Opus run.

## Not validated

- The kept rules' short forms were measured on Opus only, one run per task, with no full-file Opus arm beside them.
- Four of the five tasks also chose the rules; E alone is held out.
- Whether a lead session (Discuss, Spec, Wrap) misses what left the default context: no task exercised one.

## Next step

None for this lot. A regression shows as a gate failure that costs many turns, or a naming or design finding in a
review that the cut rule covered: restore that rule's line then.

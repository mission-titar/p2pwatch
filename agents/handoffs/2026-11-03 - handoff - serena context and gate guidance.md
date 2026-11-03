# Handoff: Serena's context measured, the gate names every red check (tier Direct)

## Current state

- **The gate continues past a failing static check**: `lint-all` and the per-package checks carry
  `ignore_fail = "return_non_zero"`, so one run names every failed subtask in its last line
  (`Subtasks 'lint', 'type-check' returned non-zero exit status`); `test` stays strict, since `_unit-coverage-check`
  reads a complete `.coverage`. A green `poe check` ends with `GATE GREEN`, printed by a last subtask that a red run
  never reaches. Proven with a planted module breaking ruff, mypy and vulture: all 41 subtasks ran, the three were named.
- **The free space meter's test** no longer compares two live reads for equality: the reading lies between two direct
  reads around it.
- **`.claude/CLAUDE.md` is 8.8 KB**: the lines the tree shows are gone (the docs list, the release workflow's
  mechanics, the gate's rationale, the Docker Desktop caveat, "use the current docs", which context7's own MCP
  instruction states), and one measured line is in: symbols through Serena, in a sentence, before Hard rules.
- **The operator's home is on the light Serena setup**: Serena's `activate` and `remind` hooks removed
  (`auto-approve` kept), the context `claude-code-light` (`~/.serena/contexts/`, five lines on what the tools are for)
  pointed by `~/.claude.json`, the manual shortened by `~/.serena/prompt_templates/system_prompt.yml`
  (`cc_system_prompt_override` kept verbatim). Also, outside this measurement: the four global rules cut from 3.3 KB to
  0.7 KB (`context7.md` deleted), `AskUserQuestion` denied by a permission rule, a `PreToolUse` hook refusing an em-dash
  or an en-dash in an Edit, a Write or a `git commit`.
- **The harness** is in `agents/reference/2026-11-03-serena-context-harness/`: briefs, scripts, the light context and
  prompts, the usage readings. Its raw outputs stayed in the session's scratchpad.

## Why

The session transcripts of this repository (670 files, teammates included) showed Serena's `remind` hook refusing
1 393 tool calls (225 reads, 1 168 greps) in 506 of them, each refusal a turn spent to re-issue the same call; its
thresholds are three consecutive calls, hard-coded in `serena/hooks.py`, on every tool. Among 2 587 `poe check` runs,
444 were red (351 at `lint-all`, 93 at the tests), 538 were piped through `tail`, `grep` or `head`, and the five Opus fix
loops of the previous lot re-ran a green gate 7 times in 24 runs to read an exit code lost in the pipe. The ruff codes
that fail most, `PLR0917` (299) and `TID251` (291), are not auto-fixable, so a formatter hook would gain little.

## Method

Two arms, Sonnet, one run per task, from a worktree of this lot's branch, `claude -p` with `SERENA_HOME` set to a home
per run (its `serena_config.yml` with the dashboard off, `language_servers` symlinked to the operator's), the
`--project-from-cwd` server bound to the worktree, a canary line proving the instruction file was read. **Full**: the
operator's setup, Serena's `claude-code` context and its three hooks. **Light**: the `claude-code-light` context, the
short manual, no hook, the Serena line in `.claude/CLAUDE.md`. Tasks A to E of the previous lot plus F, a rename of
three run state port methods across declarations, overrides, fakes and tests, with a leftover check (`git grep` of
the old names, proven to find 33 lines on the unrenamed tree). Each run stopped at its package's tests, the gate ran
check by check, then the session was resumed until `poe check` passed.

## Measured

| | Light | Full |
|---|---|---|
| Cost to green, 6 runs | 8.22 $ | 9.45 $ |
| Turns | 356 | 402 |
| Serena calls | 3 | 3 |
| Calls refused by the hook | 0 | 9 |
| Runs red at the first gate | 5 of 6 | 5 of 6 |

- The three Serena calls are the same on both sides: `rename_symbol` three times on task F, no leftover, the gate green
  at the first pass. No Serena call on any of the five additive tasks, hook or not.
- Per task (cost to green, light / full): A 1.73 / 2.74 $, B 1.25 / 1.32, C 2.74 / 2.75, D 0.95 / 1.00, E 1.06 / 1.10,
  F 0.49 / 0.52. The gap is task A's, one run each.
- Two dry runs of task D before the arms were settled (the user's context, hooks off then on): 0 Serena calls in
  both, the hook refusing one call; the `CRITICAL` server instruction alone did not make Sonnet read the manual.
- The new gate in the fix loops: `check:lint', 'format-check'` named together at one run, `GATE GREEN` read at the end,
  6 to 22 fix turns per loop.
- Plan usage: 36 % to 56 % of the 5-hour window and 45 % to 47 % of the week over the 12 runs, their fix loops, two dry
  runs and the lead session's own work.

## Pitfalls learned

- **`SERENA_HOME` is honoured by the server and by `serena-hooks`**, so a home per run keeps the operator's
  `serena_config.yml` free of the worktrees `--project-from-cwd` would register.
- **A Monitor script runs under zsh**: an unmatched glob aborts it (`no matches found`); wrap it in `bash -c` with
  `nullglob`.
- **The `remind` hook refused the lead's own commands five times** in this session, on transcripts, YAML and Serena's
  own source, where no symbolic tool applies.
- **The hooks run headless**: a `claude -p` session gets the SessionStart injection and the PreToolUse refusals as an
  interactive one does.

## Not validated

- One run per task and per arm; Opus not run on the light arm.
- The Serena line in `.claude/CLAUDE.md` and the short context were measured together, not apart.
- Whether a lead session (Discuss, Spec, Wrap) misses what left `.claude/CLAUDE.md`: no task exercised one.
- The long-dash hook on a heredoc commit message: tested on a sample call, not in a session.

## Next step

None for this lot. A regression shows as a rename with leftovers in a review, or a teammate grepping for references
where the language server was needed: restore the `remind` hook on `Bash` alone then, as Serena documents it.

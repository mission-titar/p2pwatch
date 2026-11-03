#!/usr/bin/env bash
# run_one.sh <arm> <task> <rep> <model>: one headless session on the task's brief, from its worktree, Serena bound to it.
set -uo pipefail
S=$(cd "$(dirname "$0")" && pwd); R="$1-$2-$3"; W="$S/runs/$R"; O="$S/out/$R-$4"; mkdir -p "$O"
mapfile -t FLAGS < <(bash "$S/arm_flags.sh" "$1")
cd "$W" || exit 1
date +%s > "$O/start"
SERENA_HOME="$S/homes/$R" claude -p "$(cat "$S/briefs/$2"*.txt)" --model "$4" --output-format stream-json --verbose \
  --permission-mode acceptEdits "${FLAGS[@]}" \
  --allowedTools Read Edit Write Glob Grep mcp__serena "Bash(uv run:*)" "Bash(cd:*)" "Bash(git diff:*)" "Bash(git status:*)" "Bash(git log:*)" "Bash(git show:*)" "Bash(git grep:*)" "Bash(ls:*)" "Bash(cat:*)" "Bash(grep:*)" "Bash(rg:*)" "Bash(find:*)" "Bash(head:*)" "Bash(tail:*)" "Bash(sed -n:*)" "Bash(wc:*)" \
  > "$O/session.jsonl" 2> "$O/session.err"
echo $? > "$O/exit"; date +%s > "$O/end"

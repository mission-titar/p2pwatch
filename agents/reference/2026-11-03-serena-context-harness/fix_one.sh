#!/usr/bin/env bash
# fix_one.sh <arm> <task> <rep> <model>: resumes the run's session until `poe check` passes, then measures again.
set -uo pipefail
S=$(cd "$(dirname "$0")" && pwd); R="$1-$2-$3"; W="$S/runs/$R"; O="$S/out/$R-$4"
mapfile -t FLAGS < <(bash "$S/arm_flags.sh" "$1")
id=$(python3 -c "import json,sys;print(next(json.loads(l)['session_id'] for l in open(sys.argv[1]) if 'session_id' in l))" "$O/session.jsonl")
cd "$W" || exit 1
date +%s > "$O/fix.start"
SERENA_HOME="$S/homes/$R" claude -p "Now run \`uv run poe check\` from the repository root and fix every problem it reports, until it passes. Run one command per Bash call. Do not commit and do not push. Finish with a short report of what you fixed." \
  --resume "$id" --model "$4" --output-format stream-json --verbose \
  --permission-mode acceptEdits "${FLAGS[@]}" \
  --allowedTools Read Edit Write Glob Grep mcp__serena "Bash(uv run:*)" "Bash(cd:*)" "Bash(git diff:*)" "Bash(git status:*)" "Bash(git log:*)" "Bash(git show:*)" "Bash(git grep:*)" "Bash(ls:*)" "Bash(cat:*)" "Bash(grep:*)" "Bash(rg:*)" "Bash(find:*)" "Bash(head:*)" "Bash(tail:*)" "Bash(sed -n:*)" "Bash(wc:*)" \
  > "$O/fix.jsonl" 2> "$O/fix.err"
echo $? > "$O/fix.exit"; date +%s > "$O/fix.end"
GATE_SUFFIX=-fixed bash "$S/measure.sh" "$1" "$2" "$3" > /dev/null

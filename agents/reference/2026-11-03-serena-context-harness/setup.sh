#!/usr/bin/env bash
# setup.sh <arm> <task> <rep>: a worktree of the lot's branch with the arm's instruction file, synced, and a Serena home of its own.
set -euo pipefail
S=$(cd "$(dirname "$0")" && pwd); REPO=/home/geoffrey/Repositories/emule-indexer; BRANCH=chore/gate-guidance-context-trim
R="$1-$2-$3"; W="$S/runs/$R"; H="$S/homes/$R"
git -C "$REPO" worktree add --detach "$W" "$BRANCH" >/dev/null
python3 "$S/make_variant.py" "$1" "$W"
( cd "$W" && uv sync --dev --quiet )
git -C "$W" add -A .claude && git -C "$W" -c user.name=trim -c user.email=trim@local commit -qm "arm $1"
mkdir -p "$H" && ln -sfn "$HOME/.serena/language_servers" "$H/language_servers"
sed -e 's/^web_dashboard: true/web_dashboard: false/' -e 's/^web_dashboard_open_on_launch: true/web_dashboard_open_on_launch: false/' \
    -e '/^projects:/,/^[a-z_]*:/{ /^- /d }' "$HOME/.serena/serena_config.yml" > "$H/serena_config.yml"
[ "$1" = light ] && mkdir -p "$H/prompt_templates" && cp "$S/light-system-prompt.yml" "$H/prompt_templates/system_prompt.yml"
echo "$W"

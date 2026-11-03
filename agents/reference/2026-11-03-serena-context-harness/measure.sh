#!/usr/bin/env bash
# measure.sh <arm> <task> <rep>: every check of the measurement gate, each on its own, into gate/.
set -uo pipefail
S=$(cd "$(dirname "$0")" && pwd); W="$S/runs/$1-$2-$3"; G="$S/gate/$1-$2-$3${GATE_SUFFIX:-}"; mkdir -p "$G"
cd "$W" || exit 1
PKG=crawler; [ "$2" = D ] && PKG=amule; [ "$2" = E ] && PKG=template_checks
check() { local name=$1; shift; ( "$@" ) > "$G/$name.log" 2>&1; echo "$name $?" >> "$G/summary"; }
: > "$G/summary"
git status --short > "$G/files.txt"; git diff --stat > "$G/diffstat.txt"
check ruff uv run ruff check --output-format concise .
check format uv run ruff format --check .
check deps uv run poe dependency-check
check patterns uv run ast-grep scan --json=compact
check arch uv run poe architecture-check
check dead uv run poe dead-code-check
check mypy uv run poe type-check
check pyrefly uv run poe pyrefly-check
check sql uv run poe sql-lint
check templates uv run poe template-check
check pytest bash -c "cd packages/$PKG && uv run pytest -q -p no:randomly"
check unitcov bash -c "cd packages/$PKG && uv run python -m coverage_checks unit-coverage"
[ "$2" = F ] && check leftovers bash -c "! git grep -n -E '(def |\\.)(is_paused|wait_until_resumed|set_paused)\\(' -- . ':!agents'"
[ "$PKG" != crawler ] && check structure bash -c "cd packages/crawler && uv run pytest -q --no-cov tests/test_port_files.py tests/test_fake_files.py tests/test_contract_subclasses.py"
cat "$G/summary"

"""Writes an arm's instruction file into a worktree: `full` as is, `light` with the Serena line."""

import sys
from pathlib import Path

CANARY = (
    "\n## Report\n\nEnd your final report with the word ORNITHORYNQUE-8 on a line of its own.\n"
)
SERENA_LINE = (
    " language server: it sees every reference and every override, `grep` sees strings. Read"
    " `.claude/rules/serena.md` before a rename.\n\n"
    " language server: it sees every reference and every override, `grep` sees strings."
    " Read `.claude/rules/serena.md` before a rename.\n\n"
)

arm, target = sys.argv[1], Path(sys.argv[2])
instructions = target / ".claude/CLAUDE.md"
text = instructions.read_text()
if arm == "light":
    marker = "## Hard rules\n\n"
    assert text.count(marker) == 1
    text = text.replace(marker, SERENA_LINE + marker)
instructions.write_text(text + CANARY)

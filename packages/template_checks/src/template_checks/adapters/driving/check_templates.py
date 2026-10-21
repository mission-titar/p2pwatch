"""The logic-free check over a templates directory, until `CheckLogicFree` replaces it."""

from pathlib import Path, PurePath

from template_checks.domain.logic_constructs import find_logic_constructs


def main(templates_dir: Path) -> int:
    """Prints each logic construct under *templates_dir*, returns 1 if there is any."""
    templates_by_path: dict[PurePath, str] = {
        template_path.relative_to(templates_dir): template_path.read_text(encoding="utf-8")
        for template_path in sorted(templates_dir.rglob("*.html"))
    }
    problems = find_logic_constructs(templates_by_path)
    for problem in problems:
        print(problem)
    return 1 if problems else 0

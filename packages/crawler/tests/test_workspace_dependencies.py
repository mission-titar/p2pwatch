"""The workspace's internal dependencies: no hexagon declares another hexagon's distribution."""

import re
import tomllib
from pathlib import Path

_PACKAGES_DIR = Path(__file__).parents[2]

# (distribution, its dependency group or "" for the runtime one, the member it depends on).
_ALLOWED_EDGES = {
    ("p2pwatch", "", "catalog-matching"),
    ("p2pwatch", "dev", "p2pwatch-testing"),
    ("p2pwatch-testing", "", "p2pwatch"),
}


def _normalized(requirement: str) -> str:
    distribution = re.match(r"[A-Za-z0-9._-]+", requirement.strip())
    assert distribution is not None, requirement
    return re.sub(r"[-_.]+", "-", distribution.group()).lower()


def _workspace_edges() -> set[tuple[str, str, str]]:
    pyprojects = [
        tomllib.loads(path.read_text()) for path in sorted(_PACKAGES_DIR.glob("*/pyproject.toml"))
    ]
    members = {_normalized(pyproject["project"]["name"]) for pyproject in pyprojects}
    edges: set[tuple[str, str, str]] = set()
    for pyproject in pyprojects:
        project = pyproject["project"]
        requirements_by_group: dict[str, list[object]] = {
            "": project.get("dependencies", []),
            **project.get("optional-dependencies", {}),
            **pyproject.get("dependency-groups", {}),
        }
        for group, requirements in requirements_by_group.items():
            for requirement in requirements:
                if isinstance(requirement, str) and _normalized(requirement) in members:
                    edges.add((_normalized(project["name"]), group, _normalized(requirement)))
    return edges


def test_only_the_crawler_and_its_test_support_depend_on_a_workspace_member() -> None:
    assert _workspace_edges() == _ALLOWED_EDGES

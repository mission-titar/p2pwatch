"""Every hexagon's port files: one port per file, named after it."""

import ast
from pathlib import Path

from tests.support.snake_case import snake_case

_PACKAGES_DIR = Path(__file__).parents[2]


def _port_files() -> list[Path]:
    return sorted(
        path
        for path in _PACKAGES_DIR.glob("*/src/*/application/ports/**/*.py")
        if path.name != "__init__.py"
    )


def _port_names(port_file: Path) -> list[str]:
    """The classes the file defines on `ABC`, which every port inherits."""
    module = ast.parse(port_file.read_text())
    return [
        node.name
        for node in module.body
        if isinstance(node, ast.ClassDef) and any(ast.unparse(base) == "ABC" for base in node.bases)
    ]


def test_each_port_file_holds_one_port_named_after_it() -> None:
    port_names_by_file = {port_file: _port_names(port_file) for port_file in _port_files()}
    port_names_by_misnamed_file = {
        str(port_file.relative_to(_PACKAGES_DIR)): port_names
        for port_file, port_names in port_names_by_file.items()
        if [snake_case(name) for name in port_names] != [port_file.stem]
    }
    assert port_names_by_file
    assert port_names_by_misnamed_file == {}

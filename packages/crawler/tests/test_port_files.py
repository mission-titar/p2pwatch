"""Every hexagon's port files: one port per file, named after it; a Writer half of a store."""

import ast
import re
from collections import defaultdict
from pathlib import Path

from tests.support.snake_case import snake_case

_PACKAGES_DIR = Path(__file__).parents[2]
_STORE_PORT_NAME = re.compile(r"(?P<thing>\w+)(?:Writer|Reader)")


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


def test_each_writer_port_has_a_reader_port_of_its_thing() -> None:
    port_names_by_package: dict[str, set[str]] = defaultdict(set)
    for port_file in _port_files():
        package = port_file.relative_to(_PACKAGES_DIR).parts[0]
        port_names_by_package[package].update(_port_names(port_file))
    writer_names = [
        name
        for names in port_names_by_package.values()
        for name in names
        if name.endswith("Writer")
    ]
    writer_names_without_reader = sorted(
        name
        for names in port_names_by_package.values()
        for name in names
        if name.endswith("Writer") and f"{name.removesuffix('Writer')}Reader" not in names
    )
    assert writer_names
    assert writer_names_without_reader == []


def _imported_port_names(module: ast.Module) -> set[str]:
    return {
        alias.asname or alias.name
        for node in module.body
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and ".application.ports." in node.module
        for alias in node.names
    }


def test_a_class_implements_the_writer_and_reader_ports_of_one_thing_at_most() -> None:
    things_by_class: dict[str, list[str]] = {}
    for file in sorted(_PACKAGES_DIR.glob("*/src/**/*.py")):
        module = ast.parse(file.read_text())
        port_names = _imported_port_names(module)
        for node in module.body:
            if isinstance(node, ast.ClassDef):
                base_names = [ast.unparse(base) for base in node.bases]
                things_by_class[f"{file.relative_to(_PACKAGES_DIR)}::{node.name}"] = sorted(
                    {
                        match["thing"]
                        for name in base_names
                        if name in port_names and (match := _STORE_PORT_NAME.fullmatch(name))
                    }
                )
    things_by_mixing_class = {
        class_name: things for class_name, things in things_by_class.items() if len(things) > 1
    }
    assert any(len(things) == 1 for things in things_by_class.values())
    assert things_by_mixing_class == {}


def test_a_class_implementing_a_writer_port_implements_its_reader_port_too() -> None:
    writer_names_by_class: dict[str, list[str]] = {}
    for file in sorted(_PACKAGES_DIR.glob("*/src/**/*.py")):
        module = ast.parse(file.read_text())
        port_names = _imported_port_names(module)
        for node in module.body:
            if isinstance(node, ast.ClassDef):
                base_names = {ast.unparse(base) for base in node.bases} & port_names
                writer_names_by_class[f"{file.relative_to(_PACKAGES_DIR)}::{node.name}"] = sorted(
                    name
                    for name in base_names
                    if name.endswith("Writer")
                    and f"{name.removesuffix('Writer')}Reader" not in base_names
                )
    writer_names_by_half_store = {
        class_name: writer_names
        for class_name, writer_names in writer_names_by_class.items()
        if writer_names
    }
    assert writer_names_by_class
    assert writer_names_by_half_store == {}

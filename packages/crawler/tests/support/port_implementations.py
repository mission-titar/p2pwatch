"""Every package's classes and the ports each implements, read from the AST."""

import ast
from dataclasses import dataclass
from functools import cache
from pathlib import Path

PACKAGES_DIR = Path(__file__).parents[3]
_SOURCE_DIRS_BY_MODULE = {
    path.name: path for path in PACKAGES_DIR.glob("*/src/*") if (path / "__init__.py").is_file()
}
PORTS_RING = ("application", "ports")


@dataclass(frozen=True)
class ClassDefinition:
    file: Path
    name: str


@cache
def parsed(file: Path) -> ast.Module:
    return ast.parse(file.read_text())


def package_dir(file: Path) -> Path:
    return PACKAGES_DIR / file.relative_to(PACKAGES_DIR).parts[0]


def _module_file(module: str, importer_package_dir: Path) -> Path | None:
    """The first-party file of `module`, `tests` being the importing package's."""
    top_module, *submodules = module.split(".")
    root = (
        importer_package_dir / "tests"
        if top_module == "tests"
        else _SOURCE_DIRS_BY_MODULE.get(top_module)
    )
    if root is None:
        return None
    file = root.joinpath(*submodules).with_suffix(".py")
    return file if file.is_file() else None


def source_ring(file: Path) -> tuple[str, ...]:
    directories = file.relative_to(package_dir(file) / "src").parts[1:-1]
    return (
        directories[:2] if directories[:1] in (("adapters",), ("application",)) else directories[:1]
    )


def _is_port(definition: ClassDefinition) -> bool:
    file = definition.file
    return file.is_relative_to(package_dir(file) / "src") and source_ring(file) == PORTS_RING


def class_def(definition: ClassDefinition) -> ast.ClassDef:
    return next(
        node
        for node in ast.walk(parsed(definition.file))
        if isinstance(node, ast.ClassDef) and node.name == definition.name
    )


def _first_party_bases(file: Path, class_node: ast.ClassDef) -> list[ClassDefinition]:
    module = parsed(file)
    imported_by_name = {
        alias.asname or alias.name: (node.module, alias.name)
        for node in ast.walk(module)
        if isinstance(node, ast.ImportFrom) and node.module is not None
        for alias in node.names
    }
    class_names = {node.name for node in module.body if isinstance(node, ast.ClassDef)}
    bases: list[ClassDefinition] = []
    for base in class_node.bases:
        base_name = base.value if isinstance(base, ast.Subscript) else base
        if not isinstance(base_name, ast.Name):
            continue
        if base_name.id in class_names:
            bases.append(ClassDefinition(file, base_name.id))
        elif base_name.id in imported_by_name:
            module_name, class_name = imported_by_name[base_name.id]
            base_file = _module_file(module_name, package_dir(file))
            if base_file is not None:
                bases.append(ClassDefinition(base_file, class_name))
    return bases


def implemented_ports(file: Path, class_node: ast.ClassDef) -> set[ClassDefinition]:
    """The ports the class implements, through any first-party base."""
    return {port for base in _first_party_bases(file, class_node) for port in ports(base)}


def ports(definition: ClassDefinition) -> set[ClassDefinition]:
    if _is_port(definition):
        return {definition}
    return implemented_ports(definition.file, class_def(definition))


def class_definitions(file: Path) -> list[ClassDefinition]:
    return [
        ClassDefinition(file, node.name)
        for node in parsed(file).body
        if isinstance(node, ast.ClassDef)
    ]


def shown(definition: ClassDefinition) -> str:
    return f"{definition.file.relative_to(PACKAGES_DIR)}::{definition.name}"

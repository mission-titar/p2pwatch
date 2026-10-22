"""Every package's doubles: one per file, named after it, in the ring of what it replaces."""

import ast
from collections import defaultdict
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from tests.support.snake_case import snake_case

_PACKAGES_DIR = Path(__file__).parents[2]
_SOURCE_DIRS_BY_MODULE = {
    path.name: path for path in _PACKAGES_DIR.glob("*/src/*") if (path / "__init__.py").is_file()
}
_PORTS_RING = ("application", "ports")
# A double implementing no port replaces what an adapter receives, or an outside system (the root).
_PORTLESS_RINGS = {("adapters", "driven"), ()}
# A double replaces the outermost implementation of its port, the one the code under test is handed.
_RINGS_OUTERMOST_FIRST = ("composition", "adapters", "application")


@dataclass(frozen=True)
class _ClassDefinition:
    file: Path
    name: str


@cache
def _parsed(file: Path) -> ast.Module:
    return ast.parse(file.read_text())


def _package_dir(file: Path) -> Path:
    return _PACKAGES_DIR / file.relative_to(_PACKAGES_DIR).parts[0]


def _module_file(module: str, package_dir: Path) -> Path | None:
    """The first-party file of `module`, `tests` being the importing package's."""
    top_module, *submodules = module.split(".")
    root = (
        package_dir / "tests" if top_module == "tests" else _SOURCE_DIRS_BY_MODULE.get(top_module)
    )
    if root is None:
        return None
    file = root.joinpath(*submodules).with_suffix(".py")
    return file if file.is_file() else None


def _source_ring(file: Path) -> tuple[str, ...]:
    directories = file.relative_to(_package_dir(file) / "src").parts[1:-1]
    return (
        directories[:2] if directories[:1] in (("adapters",), ("application",)) else directories[:1]
    )


def _is_port(definition: _ClassDefinition) -> bool:
    file = definition.file
    return file.is_relative_to(_package_dir(file) / "src") and _source_ring(file) == _PORTS_RING


def _class_def(definition: _ClassDefinition) -> ast.ClassDef:
    return next(
        node
        for node in ast.walk(_parsed(definition.file))
        if isinstance(node, ast.ClassDef) and node.name == definition.name
    )


def _first_party_bases(file: Path, class_def: ast.ClassDef) -> list[_ClassDefinition]:
    module = _parsed(file)
    imported_by_name = {
        alias.asname or alias.name: (node.module, alias.name)
        for node in ast.walk(module)
        if isinstance(node, ast.ImportFrom) and node.module is not None
        for alias in node.names
    }
    class_names = {node.name for node in module.body if isinstance(node, ast.ClassDef)}
    bases: list[_ClassDefinition] = []
    for base in class_def.bases:
        base_name = base.value if isinstance(base, ast.Subscript) else base
        if not isinstance(base_name, ast.Name):
            continue
        if base_name.id in class_names:
            bases.append(_ClassDefinition(file, base_name.id))
        elif base_name.id in imported_by_name:
            module_name, class_name = imported_by_name[base_name.id]
            base_file = _module_file(module_name, _package_dir(file))
            if base_file is not None:
                bases.append(_ClassDefinition(base_file, class_name))
    return bases


def _implemented_ports(file: Path, class_def: ast.ClassDef) -> set[_ClassDefinition]:
    """The ports the class implements, through any first-party base."""
    return {port for base in _first_party_bases(file, class_def) for port in _ports(base)}


def _ports(definition: _ClassDefinition) -> set[_ClassDefinition]:
    if _is_port(definition):
        return {definition}
    return _implemented_ports(definition.file, _class_def(definition))


def _class_definitions(file: Path) -> list[_ClassDefinition]:
    return [
        _ClassDefinition(file, node.name)
        for node in _parsed(file).body
        if isinstance(node, ast.ClassDef)
    ]


def _is_record(definition: _ClassDefinition) -> bool:
    """A dataclass a double returns or keeps, which lives in its double's file."""
    class_def = _class_def(definition)
    decorators = [ast.unparse(decorator) for decorator in class_def.decorator_list]
    return not class_def.bases and any(
        decorator.startswith("dataclass") for decorator in decorators
    )


def _doubles_by_file() -> dict[Path, list[_ClassDefinition]]:
    fakes_files = sorted(
        file for file in _PACKAGES_DIR.glob("*/tests/fakes/**/*.py") if file.name != "__init__.py"
    )
    return {
        file: [definition for definition in _class_definitions(file) if not _is_record(definition)]
        for file in fakes_files
    }


def _source_rings_by_port() -> dict[_ClassDefinition, set[tuple[str, ...]]]:
    """The rings of `src` holding a class that implements each port."""
    rings_by_port: dict[_ClassDefinition, set[tuple[str, ...]]] = defaultdict(set)
    for file in _PACKAGES_DIR.glob("*/src/**/*.py"):
        if _source_ring(file) == _PORTS_RING:
            continue
        for definition in _class_definitions(file):
            for port in _ports(definition):
                rings_by_port[port].add(_source_ring(file))
    return rings_by_port


def _outermost(rings: set[tuple[str, ...]]) -> set[tuple[str, ...]]:
    """The outermost of `rings`, none when nothing in `src` implements the port."""
    return {min(rings, key=lambda ring: _RINGS_OUTERMOST_FIRST.index(ring[0]))} if rings else set()


def _writer_reader_pair(reader_name: str) -> list[str]:
    """The sorted names of the pair whose reader is `reader_name`, which one store implements."""
    thing = reader_name.removesuffix("Reader")
    return [f"{thing}Reader", f"{thing}Writer"]


def _shown(definition: _ClassDefinition) -> str:
    return f"{definition.file.relative_to(_PACKAGES_DIR)}::{definition.name}"


def test_each_fakes_file_holds_one_double_named_after_it() -> None:
    doubles_by_file = _doubles_by_file()
    double_names_by_misnamed_file = {
        str(file.relative_to(_PACKAGES_DIR)): [double.name for double in doubles]
        for file, doubles in doubles_by_file.items()
        if [snake_case(double.name) for double in doubles] != [file.stem]
    }
    assert doubles_by_file
    assert double_names_by_misnamed_file == {}


def test_each_double_sits_in_the_ring_of_what_it_replaces() -> None:
    rings_by_port = _source_rings_by_port()
    expected_rings_by_misplaced_double: dict[str, list[str]] = {}
    for file, doubles in _doubles_by_file().items():
        ring = file.parent.relative_to(_package_dir(file) / "tests" / "fakes").parts
        for double in doubles:
            ports = _ports(double)
            expected_rings = (
                _outermost({source_ring for port in ports for source_ring in rings_by_port[port]})
                if ports
                else _PORTLESS_RINGS
            )
            if ring not in expected_rings:
                expected_rings_by_misplaced_double[_shown(double)] = sorted(
                    "/".join(expected_ring) or "." for expected_ring in expected_rings
                )
    assert expected_rings_by_misplaced_double == {}


def test_each_double_implements_one_port_or_one_writer_reader_pair() -> None:
    port_names_by_double = {
        _shown(double): sorted(port.name for port in _ports(double))
        for doubles in _doubles_by_file().values()
        for double in doubles
    }
    port_names_by_mixing_double = {
        double: port_names
        for double, port_names in port_names_by_double.items()
        if len(port_names) > 1 and port_names != _writer_reader_pair(port_names[0])
    }
    assert {1, 2} <= {len(port_names) for port_names in port_names_by_double.values()}
    assert port_names_by_mixing_double == {}


def test_a_writer_reader_pair_with_doubles_has_one_store() -> None:
    port_sets = [_ports(double) for doubles in _doubles_by_file().values() for double in doubles]
    faked_ports = set().union(*port_sets)
    faked_pairs = [
        (writer, reader)
        for writer in faked_ports
        for reader in faked_ports
        if _writer_reader_pair(reader.name) == [reader.name, writer.name]
        and _package_dir(writer.file) == _package_dir(reader.file)
    ]
    split_pairs = sorted(
        f"{writer.name}, {reader.name}"
        for writer, reader in faked_pairs
        if {writer, reader} not in port_sets
    )
    assert faked_pairs
    assert split_pairs == []


def test_no_class_under_tests_outside_its_fakes_implements_a_port() -> None:
    port_names_by_stray_class = {
        f"{file.relative_to(_PACKAGES_DIR)}::{node.name}": sorted(port.name for port in ports)
        for file in sorted(_PACKAGES_DIR.glob("*/tests/**/*.py"))
        if not file.is_relative_to(_package_dir(file) / "tests" / "fakes")
        for node in ast.walk(_parsed(file))
        if isinstance(node, ast.ClassDef) and (ports := _implemented_ports(file, node))
    }
    assert port_names_by_stray_class == {}

"""Every package's doubles: one per file, named after it, in the ring of what it replaces."""

import ast
from collections import defaultdict
from pathlib import Path

from tests.support.port_implementations import (
    PACKAGES_DIR,
    PORTS_RING,
    ClassDefinition,
    class_def,
    class_definitions,
    implemented_ports,
    package_dir,
    parsed,
    ports,
    shown,
    source_ring,
)
from tests.support.snake_case import snake_case

# A double implementing no port replaces what an adapter receives, or an outside system (the root).
_PORTLESS_RINGS = {("adapters", "driven"), ()}
# A double replaces the outermost implementation of its port, the one the code under test is handed.
_RINGS_OUTERMOST_FIRST = ("composition", "adapters", "application")


def _is_record(definition: ClassDefinition) -> bool:
    """A dataclass a double returns or keeps, which lives in its double's file."""
    class_node = class_def(definition)
    decorators = [ast.unparse(decorator) for decorator in class_node.decorator_list]
    return not class_node.bases and any(
        decorator.startswith("dataclass") for decorator in decorators
    )


def _doubles_by_file() -> dict[Path, list[ClassDefinition]]:
    # A test_*.py beside the doubles tests them and holds none.
    fakes_files = sorted(
        file
        for file in PACKAGES_DIR.glob("*/tests/fakes/**/*.py")
        if file.name != "__init__.py" and not file.name.startswith("test_")
    )
    return {
        file: [definition for definition in class_definitions(file) if not _is_record(definition)]
        for file in fakes_files
    }


def _source_rings_by_port() -> dict[ClassDefinition, set[tuple[str, ...]]]:
    """The rings of `src` holding a class that implements each port."""
    rings_by_port: dict[ClassDefinition, set[tuple[str, ...]]] = defaultdict(set)
    for file in PACKAGES_DIR.glob("*/src/**/*.py"):
        if source_ring(file) == PORTS_RING:
            continue
        for definition in class_definitions(file):
            for port in ports(definition):
                rings_by_port[port].add(source_ring(file))
    return rings_by_port


def _outermost(rings: set[tuple[str, ...]]) -> set[tuple[str, ...]]:
    """The outermost of `rings`, none when nothing in `src` implements the port."""
    return {min(rings, key=lambda ring: _RINGS_OUTERMOST_FIRST.index(ring[0]))} if rings else set()


def _writer_reader_pair(reader_name: str) -> list[str]:
    """The sorted names of the pair whose reader is `reader_name`, which one store implements."""
    thing = reader_name.removesuffix("Reader")
    return [f"{thing}Reader", f"{thing}Writer"]


def test_each_fakes_file_holds_one_double_named_after_it() -> None:
    doubles_by_file = _doubles_by_file()
    double_names_by_misnamed_file = {
        str(file.relative_to(PACKAGES_DIR)): [double.name for double in doubles]
        for file, doubles in doubles_by_file.items()
        if [snake_case(double.name) for double in doubles] != [file.stem]
    }
    assert doubles_by_file
    assert double_names_by_misnamed_file == {}


def test_each_double_sits_in_the_ring_of_what_it_replaces() -> None:
    rings_by_port = _source_rings_by_port()
    expected_rings_by_misplaced_double: dict[str, list[str]] = {}
    for file, doubles in _doubles_by_file().items():
        ring = file.parent.relative_to(package_dir(file) / "tests" / "fakes").parts
        for double in doubles:
            double_ports = ports(double)
            expected_rings = (
                _outermost(
                    {port_ring for port in double_ports for port_ring in rings_by_port[port]}
                )
                if double_ports
                else _PORTLESS_RINGS
            )
            if ring not in expected_rings:
                expected_rings_by_misplaced_double[shown(double)] = sorted(
                    "/".join(expected_ring) or "." for expected_ring in expected_rings
                )
    assert expected_rings_by_misplaced_double == {}


def test_each_double_implements_one_port_or_one_writer_reader_pair() -> None:
    port_names_by_double = {
        shown(double): sorted(port.name for port in ports(double))
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
    port_sets = [ports(double) for doubles in _doubles_by_file().values() for double in doubles]
    faked_ports = set().union(*port_sets)
    faked_pairs = [
        (writer, reader)
        for writer in faked_ports
        for reader in faked_ports
        if _writer_reader_pair(reader.name) == [reader.name, writer.name]
        and package_dir(writer.file) == package_dir(reader.file)
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
        f"{file.relative_to(PACKAGES_DIR)}::{node.name}": sorted(port.name for port in class_ports)
        for file in sorted(PACKAGES_DIR.glob("*/tests/**/*.py"))
        # A test_*.py beside the doubles holds none, so a port's implementation there strays.
        if not file.is_relative_to(package_dir(file) / "tests" / "fakes")
        or file.name.startswith("test_")
        for node in ast.walk(parsed(file))
        if isinstance(node, ast.ClassDef) and (class_ports := implemented_ports(file, node))
    }
    assert port_names_by_stray_class == {}

"""Every package's contracts: each implementation of a contracted port runs its contract."""

import ast
from pathlib import Path

from tests.support.port_implementations import (
    PACKAGES_DIR,
    PORTS_RING,
    ClassDefinition,
    class_def,
    class_definitions,
    first_party_bases,
    package_dir,
    ports,
    shown,
    source_ring,
)

# Implementations that break their port on purpose, by `shown` name, each with its reason.
_EXEMPTIONS: dict[str, str] = {
    "crawler/tests/fakes/adapters/driven/fake_no_set_state_tracked_download_store.py"
    "::FakeNoSetStateTrackedDownloadStore": "fails the test on any set_state, by design",
    "crawler/tests/fakes/adapters/driven/fake_blocking_monotonic_clock.py"
    "::FakeBlockingMonotonicClock": "sleeps for good and fails the test on any now, by design",
}


def _suites() -> list[ClassDefinition]:
    return [
        definition
        for file in sorted(PACKAGES_DIR.glob("*/tests/contracts/**/*_contract.py"))
        for definition in class_definitions(file)
        if definition.name.endswith("Contract")
    ]


def _covered_port_names(suite: ClassDefinition) -> set[str]:
    """`<Thing>Reader` and `<Thing>Writer` for `<Thing>StoreContract`, else `<Port>`."""
    port_name = suite.name.removesuffix("Contract")
    thing = port_name.removesuffix("Store")
    return {f"{thing}Reader", f"{thing}Writer"} if thing != port_name else {port_name}


def _package_ports(package: Path) -> list[ClassDefinition]:
    return [
        definition
        for file in sorted(package.glob("src/**/*.py"))
        if source_ring(file) == PORTS_RING
        for definition in class_definitions(file)
    ]


def _implementations(package: Path, covered_ports: set[ClassDefinition]) -> list[ClassDefinition]:
    """The classes of `src` and `tests/fakes` implementing one of `covered_ports`."""
    files = [
        *(file for file in package.glob("src/**/*.py") if source_ring(file) != PORTS_RING),
        *(
            file
            for file in package.glob("tests/fakes/**/*.py")
            if not file.name.startswith("test_")
        ),
    ]
    return [
        definition
        for file in sorted(files)
        for definition in class_definitions(file)
        if ports(definition) & covered_ports
    ]


def _implementations_by_suite() -> dict[ClassDefinition, list[ClassDefinition]]:
    implementations_by_suite = {}
    for suite in _suites():
        package = package_dir(suite.file)
        covered_ports = {
            port for port in _package_ports(package) if port.name in _covered_port_names(suite)
        }
        implementations_by_suite[suite] = _implementations(package, covered_ports)
    return implementations_by_suite


def _subclasses(suite: ClassDefinition) -> list[ClassDefinition]:
    return [
        definition
        for file in sorted(package_dir(suite.file).glob("tests/**/test_*.py"))
        for definition in class_definitions(file)
        if suite in first_party_bases(file, class_def(definition))
    ]


def _method_names(definition: ClassDefinition, *, abstract: bool) -> set[str]:
    return {
        node.name
        for node in class_def(definition).body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and (
            not abstract
            or any(ast.unparse(decorator) == "abstractmethod" for decorator in node.decorator_list)
        )
    }


def test_each_contract_covers_ports_of_its_package() -> None:
    suites = _suites()
    missing_port_names_by_suite = {
        shown(suite): sorted(
            _covered_port_names(suite)
            - {port.name for port in _package_ports(package_dir(suite.file))}
        )
        for suite in suites
    }
    assert suites
    assert {suite: names for suite, names in missing_port_names_by_suite.items() if names} == {}


def test_each_implementation_of_a_contracted_port_has_its_subclass_or_an_exemption() -> None:
    implementations_by_suite = _implementations_by_suite()
    expected_subclass_by_uncovered_implementation = {
        shown(implementation): f"Test{implementation.name}"
        for suite, implementations in implementations_by_suite.items()
        for implementation in implementations
        if f"Test{implementation.name}" not in {subclass.name for subclass in _subclasses(suite)}
        and shown(implementation) not in _EXEMPTIONS
    }
    assert all(implementations_by_suite.values())
    assert expected_subclass_by_uncovered_implementation == {}


def test_each_subclass_of_a_contract_defines_its_abstract_fixtures() -> None:
    abstract_names_by_suite = {suite: _method_names(suite, abstract=True) for suite in _suites()}
    undefined_names_by_subclass = {
        shown(subclass): sorted(abstract_names - _method_names(subclass, abstract=False))
        for suite, abstract_names in abstract_names_by_suite.items()
        for subclass in _subclasses(suite)
    }
    assert all(abstract_names_by_suite.values())
    assert {
        subclass: names for subclass, names in undefined_names_by_subclass.items() if names
    } == {}


def test_each_exemption_names_an_implementation_of_a_contracted_port() -> None:
    implementations = {
        shown(implementation)
        for suite_implementations in _implementations_by_suite().values()
        for implementation in suite_implementations
    }
    assert sorted(_EXEMPTIONS.keys() - implementations) == []

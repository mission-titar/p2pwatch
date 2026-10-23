"""A module's own tests: the test files named after it, in the directory mirroring its own.

A test file that tests no module fails, unless its package lists it in `tests_without_unit`.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePath

from coverage_checks.domain.package_tree import PackageTree

_UNIT_NAMES_BY_DUNDER = {"__init__": "init", "__main__": "main"}


@dataclass(frozen=True)
class ListingWithoutReason:
    """An entry of `tests_without_unit` whose reason is no text, or blank."""

    listed_path: str


@dataclass(frozen=True)
class UnitNameCollision:
    """A module named `main` or `init` beside the dunder module whose tests' names it would take."""

    module: PurePath


@dataclass(frozen=True)
class ListedTestOfModule:
    """A test file listed in `tests_without_unit`, though it tests a module."""

    test_file: PurePath
    module: PurePath


@dataclass(frozen=True)
class UnmappedTestFile:
    """A test file that tests no module, and is not listed in `tests_without_unit`."""

    test_file: PurePath


@dataclass(frozen=True)
class StaleListing:
    """An entry of `tests_without_unit` that names no test file."""

    listed_path: str


type TreeProblem = (
    ListingWithoutReason | UnitNameCollision | ListedTestOfModule | UnmappedTestFile | StaleListing
)


@dataclass(frozen=True)
class OwnTests:
    """Each module's own test files, the counts of test files mapped and listed, what is wrong."""

    test_files_by_module: Mapping[PurePath, tuple[PurePath, ...]]
    mapped_test_count: int
    listed_test_count: int
    problems: tuple[TreeProblem, ...]


def find_own_tests(package_tree: PackageTree) -> OwnTests:
    """Map each test file of *package_tree* to its module, in path order."""
    modules = sorted(package_tree.modules)
    test_files = sorted(package_tree.test_files)
    tests_without_unit = package_tree.tests_without_unit
    problems: list[TreeProblem] = [
        ListingWithoutReason(listed_path)
        for listed_path, reason in tests_without_unit.items()
        if not isinstance(reason, str) or not reason.strip()
    ]
    problems += [
        UnitNameCollision(module)
        for module in modules
        if module.stem in _UNIT_NAMES_BY_DUNDER.values()
        and module.with_name(f"__{module.stem}__.py") in modules
    ]
    test_files_by_module: dict[PurePath, list[PurePath]] = {module: [] for module in modules}
    listed_test_count = 0
    for test_file in test_files:
        module = _tested_module(test_file, modules)
        is_listed = any(_lists(listed_path, test_file) for listed_path in tests_without_unit)
        if module is not None and is_listed:
            problems.append(ListedTestOfModule(test_file, module))
        elif module is not None:
            test_files_by_module[module].append(test_file)
        elif is_listed:
            listed_test_count += 1
        else:
            problems.append(UnmappedTestFile(test_file))
    problems += [
        StaleListing(listed_path)
        for listed_path in tests_without_unit
        if not any(_lists(listed_path, test_file) for test_file in test_files)
    ]
    return OwnTests(
        test_files_by_module={
            module: tuple(files) for module, files in test_files_by_module.items()
        },
        mapped_test_count=sum(len(files) for files in test_files_by_module.values()),
        listed_test_count=listed_test_count,
        problems=tuple(problems),
    )


def _tested_module(test_file: PurePath, modules: Sequence[PurePath]) -> PurePath | None:
    """The module of the mirrored directory whose name the test file's is, or extends with `_`."""
    tested_name = test_file.stem.removeprefix("test_")
    directory = test_file.parent.relative_to("tests")
    matching_modules = [
        module
        for module in modules
        if PurePath(*module.parent.parts[2:]) == directory
        and (tested_name + "_").startswith(_unit_name(module) + "_")
    ]
    return max(matching_modules, key=lambda module: len(_unit_name(module)), default=None)


def _unit_name(module: PurePath) -> str:
    return _UNIT_NAMES_BY_DUNDER.get(module.stem, module.stem)


def _lists(listed_path: str, test_file: PurePath) -> bool:
    """Whether *listed_path* is the test file, or a directory above it."""
    return listed_path == test_file.as_posix() or (
        listed_path.endswith("/") and test_file.as_posix().startswith(listed_path)
    )

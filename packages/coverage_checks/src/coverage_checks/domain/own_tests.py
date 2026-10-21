"""A module's own tests: the test files named after it, in the directory mirroring its own.

A test file that tests no module fails, unless its package lists it in `tests_without_unit`.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePath

from coverage_checks.domain.package_tree import PackageTree

_UNIT_NAMES_BY_DUNDER = {"__init__": "init", "__main__": "main"}


@dataclass(frozen=True)
class OwnTests:
    """Each module's own test files, the counts of test files mapped and listed, what is wrong."""

    test_files_by_module: Mapping[PurePath, tuple[PurePath, ...]]
    mapped_test_count: int
    listed_test_count: int
    problems: tuple[str, ...]


def find_own_tests(package_tree: PackageTree) -> OwnTests:
    """Map each test file of *package_tree* to its module, in path order."""
    modules = sorted(package_tree.modules)
    test_files = sorted(package_tree.test_files)
    tests_without_unit = package_tree.tests_without_unit
    problems = [
        f"{listed_path}: listed in tests_without_unit without its reason"
        for listed_path, reason in tests_without_unit.items()
        if not isinstance(reason, str) or not reason.strip()
    ]
    problems += [
        f"{module}: its tests would be named like those of __{module.stem}__.py beside it;"
        " rename it"
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
            problems.append(f"{test_file}: listed in tests_without_unit, but tests {module}")
        elif module is not None:
            test_files_by_module[module].append(test_file)
        elif is_listed:
            listed_test_count += 1
        else:
            problems.append(
                f"{test_file}: tests no module of src; name it after the module it tests, or list"
                " it in [tool.coverage_checks] tests_without_unit with its reason"
            )
    problems += [
        f"{listed_path}: listed in tests_without_unit, but names no test file"
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

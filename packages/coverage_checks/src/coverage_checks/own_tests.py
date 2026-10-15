"""A module's own tests: the test files named after it, in the directory mirroring its own.

A test file that tests no module fails, unless its package lists it in `tests_without_unit`.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

_UNIT_NAMES_BY_DUNDER = {"__init__": "init", "__main__": "main"}


@dataclass(frozen=True)
class OwnTests:
    """Each module's own test files, the counts of test files mapped and listed, what is wrong."""

    test_files_by_module: Mapping[Path, tuple[Path, ...]]
    mapped_test_count: int
    listed_test_count: int
    problems: tuple[str, ...]


def find_own_tests(tests_without_unit: Mapping[str, object]) -> OwnTests:
    """Map each `tests/**/test_*.py` of the package in the working directory to its module."""
    modules = sorted(Path("src").glob("*/**/*.py"))
    test_files = sorted(Path("tests").rglob("test_*.py"))
    problems = [
        f"{entry}: listed in tests_without_unit without its reason"
        for entry, reason in tests_without_unit.items()
        if not isinstance(reason, str) or not reason.strip()
    ]
    problems += [
        f"{module}: its tests would be named like those of __{module.stem}__.py beside it;"
        " rename it"
        for module in modules
        if module.stem in _UNIT_NAMES_BY_DUNDER.values()
        and module.with_name(f"__{module.stem}__.py") in modules
    ]
    test_files_by_module: dict[Path, list[Path]] = {module: [] for module in modules}
    listed_test_count = 0
    for test_file in test_files:
        module = _tested_module(test_file, modules)
        is_listed = any(_lists(entry, test_file) for entry in tests_without_unit)
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
        f"{entry}: listed in tests_without_unit, but names no test file"
        for entry in tests_without_unit
        if not any(_lists(entry, test_file) for test_file in test_files)
    ]
    return OwnTests(
        test_files_by_module={
            module: tuple(files) for module, files in test_files_by_module.items()
        },
        mapped_test_count=sum(len(files) for files in test_files_by_module.values()),
        listed_test_count=listed_test_count,
        problems=tuple(problems),
    )


def _tested_module(test_file: Path, modules: Sequence[Path]) -> Path | None:
    """The module of the mirrored directory whose name the test file's is, or extends with `_`."""
    tested_name = test_file.stem.removeprefix("test_")
    directory = test_file.parent.relative_to("tests")
    candidates = [
        module
        for module in modules
        if Path(*module.parent.parts[2:]) == directory
        and (tested_name + "_").startswith(_unit_name(module) + "_")
    ]
    return max(candidates, key=lambda module: len(_unit_name(module)), default=None)


def _unit_name(module: Path) -> str:
    return _UNIT_NAMES_BY_DUNDER.get(module.stem, module.stem)


def _lists(entry: str, test_file: Path) -> bool:
    """Whether a `tests_without_unit` entry names the test file, or a directory above it."""
    return entry == test_file.as_posix() or (
        entry.endswith("/") and test_file.as_posix().startswith(entry)
    )

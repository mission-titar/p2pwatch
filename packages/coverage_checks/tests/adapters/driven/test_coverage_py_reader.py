"""Tests for the reader of a package's `.coverage`, recorded here as pytest-cov records it."""

import importlib.util
from collections.abc import Callable, Mapping
from pathlib import Path, PurePath
from types import ModuleType

import pytest
from coverage import Coverage

from coverage_checks.adapters.driven.coverage_py_reader import CoveragePyTestCoverageReader

SIZES = """\
LIMIT = 10


def is_short(size):
    if size < LIMIT:
        return True
    return False
"""

type Call = Callable[[Mapping[str, ModuleType]], object]


def _measure(
    package_directory: Path,
    source_by_module: Mapping[str, str],
    calls_by_context: Mapping[str, Call],
    *,
    branch: bool = True,
) -> None:
    """Import the modules, then run each call under its context, as pytest-cov's per-test contexts.

    A call reads each module by its name: `lambda modules: modules["sizes"].is_short(3)`."""
    for module, source in source_by_module.items():
        (package_directory / module).parent.mkdir(parents=True, exist_ok=True)
        (package_directory / module).write_text(source)
    coverage = Coverage(
        data_file=str(package_directory / ".coverage"),
        branch=branch,
        config_file=False,
        source=[str(package_directory / "src")],
    )
    coverage.start()
    try:
        modules_by_name: dict[str, ModuleType] = {}
        for module in source_by_module:
            spec = importlib.util.spec_from_file_location(
                PurePath(module).stem, package_directory / module
            )
            assert spec is not None and spec.loader is not None
            modules_by_name[spec.name] = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modules_by_name[spec.name])
        for context, call in calls_by_context.items():
            coverage.switch_context(context)
            call(modules_by_name)
    finally:
        coverage.stop()
    coverage.save()


def _reader(package_directory: Path, pyproject: str = "") -> CoveragePyTestCoverageReader:
    (package_directory / "pyproject.toml").write_text(pyproject)
    report_directory = package_directory / "report"
    report_directory.mkdir()
    return CoveragePyTestCoverageReader(
        package_directory=package_directory,
        data_file=package_directory / ".coverage",
        report_directory=report_directory,
    )


def test_read_test_coverage_reads_what_the_run_and_the_own_tests_ran(tmp_path: Path) -> None:
    _measure(
        tmp_path,
        {"src/pkg/sizes.py": SIZES},
        {
            "tests/test_sizes.py::test_short|run": lambda modules: modules["sizes"].is_short(3),
            "tests/test_sizes_long.py::test_long|run": lambda modules: modules["sizes"].is_short(
                30
            ),
        },
    )

    test_coverage = _reader(tmp_path).read_test_coverage(
        PurePath("src/pkg/sizes.py"), (PurePath("tests/test_sizes.py"),)
    )

    assert test_coverage.statements == test_coverage.statements_run == {1, 4, 5, 6, 7}
    assert test_coverage.branches == test_coverage.branches_run == {(5, 6), (5, 7)}
    assert test_coverage.statements_run_by_own_tests == {5, 6}
    assert test_coverage.branches_run_by_own_tests == {(5, 6)}


def test_a_module_without_own_test_files_has_nothing_run_by_them(tmp_path: Path) -> None:
    _measure(
        tmp_path,
        {"src/pkg/sizes.py": SIZES},
        {"tests/test_other.py::test_short|run": lambda modules: modules["sizes"].is_short(3)},
    )

    test_coverage = _reader(tmp_path).read_test_coverage(PurePath("src/pkg/sizes.py"), ())

    assert test_coverage.statements_run == {1, 4, 5, 6}
    assert test_coverage.statements_run_by_own_tests == set()
    assert test_coverage.branches_run_by_own_tests == set()


def test_the_package_s_coverage_config_excludes_its_lines(tmp_path: Path) -> None:
    guarded = """\
DEBUG = False

if DEBUG:
    import pdb


def first(names):
    return names[0]
"""
    _measure(
        tmp_path,
        {"src/pkg/guarded.py": guarded},
        {"tests/test_guarded.py::test_first|run": lambda modules: modules["guarded"].first("a")},
    )
    reader = _reader(tmp_path, '[tool.coverage.report]\nexclude_also = ["if DEBUG:"]\n')

    test_coverage = reader.read_test_coverage(
        PurePath("src/pkg/guarded.py"), (PurePath("tests/test_guarded.py"),)
    )

    assert test_coverage.statements == {1, 7, 8}


@pytest.mark.parametrize(
    "branch,contexts,has_per_test_branch_coverage",
    [
        (True, ["tests/test_sizes.py::test_short|run"], True),
        (True, [], False),
        (False, ["tests/test_sizes.py::test_short|run"], False),
    ],
    ids=["per-test-branches", "no-test-context", "no-branch"],
)
def test_has_per_test_branch_coverage_needs_branches_and_a_test_s_context(
    tmp_path: Path, branch: bool, contexts: list[str], has_per_test_branch_coverage: bool
) -> None:
    _measure(
        tmp_path,
        {"src/pkg/sizes.py": SIZES},
        {context: lambda modules: modules["sizes"].is_short(3) for context in contexts},
        branch=branch,
    )

    assert _reader(tmp_path).has_per_test_branch_coverage() is has_per_test_branch_coverage


def test_a_missing_data_file_has_no_per_test_branch_coverage(tmp_path: Path) -> None:
    assert _reader(tmp_path).has_per_test_branch_coverage() is False

"""Tests for the reader of a package's `.coverage`, recorded here as pytest-cov records it."""

import gc
import importlib.util
import re
from collections.abc import Mapping
from pathlib import Path, PurePath
from types import ModuleType
from typing import Protocol

import pytest
from coverage import Coverage

from coverage_checks.adapters.driven.coverage_py_test_coverage_reader import (
    CoveragePyTestCoverageReader,
)
from coverage_checks.domain.broken_input_error import BrokenInputError

SIZES = """\
LIMIT = 10


def is_short(size):
    if size < LIMIT:
        return True
    return False
"""


class MeasuredModulesCall(Protocol):
    def __call__(self, modules: Mapping[str, ModuleType], /) -> object: ...


def _no_per_test_coverage_message(package_directory: Path) -> str:
    return (
        f"{package_directory / '.coverage'}: no per-test branch coverage; run this package's"
        " pytest first, with branch coverage and --cov-context=test"
    )


def _measure(
    package_directory: Path,
    *,
    source_by_module: Mapping[str, str],
    calls_by_context: Mapping[str, MeasuredModulesCall],
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


def _reader(package_directory: Path, *, pyproject: str = "") -> CoveragePyTestCoverageReader:
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
        source_by_module={"src/pkg/sizes.py": SIZES},
        calls_by_context={
            "tests/test_sizes.py::test_short|run": lambda modules: modules["sizes"].is_short(3),
            "tests/test_sizes_long.py::test_long|run": lambda modules: modules["sizes"].is_short(
                30
            ),
        },
    )

    test_coverage = _reader(tmp_path).read_test_coverage_by_module(
        {PurePath("src/pkg/sizes.py"): (PurePath("tests/test_sizes.py"),)}
    )[PurePath("src/pkg/sizes.py")]

    assert test_coverage.statements == test_coverage.statements_run == {1, 4, 5, 6, 7}
    assert test_coverage.branches == test_coverage.branches_run == {(5, 6), (5, 7)}
    assert test_coverage.statements_run_by_own_tests == {5, 6}
    assert test_coverage.branches_run_by_own_tests == {(5, 6)}


def test_a_module_without_own_test_files_has_nothing_run_by_them(tmp_path: Path) -> None:
    _measure(
        tmp_path,
        source_by_module={"src/pkg/sizes.py": SIZES},
        calls_by_context={
            "tests/test_other.py::test_short|run": lambda modules: modules["sizes"].is_short(3)
        },
    )

    test_coverage = _reader(tmp_path).read_test_coverage_by_module(
        {PurePath("src/pkg/sizes.py"): ()}
    )[PurePath("src/pkg/sizes.py")]

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
        source_by_module={"src/pkg/guarded.py": guarded},
        calls_by_context={
            "tests/test_guarded.py::test_first|run": lambda modules: modules["guarded"].first("a")
        },
    )
    reader = _reader(tmp_path, pyproject='[tool.coverage.report]\nexclude_also = ["if DEBUG:"]\n')

    test_coverage = reader.read_test_coverage_by_module(
        {PurePath("src/pkg/guarded.py"): (PurePath("tests/test_guarded.py"),)}
    )[PurePath("src/pkg/guarded.py")]

    assert test_coverage.statements == {1, 7, 8}


@pytest.mark.parametrize(
    "branch,contexts",
    [(True, []), (False, ["tests/test_sizes.py::test_short|run"])],
    ids=["no-test-context", "no-branch"],
)
def test_a_run_without_per_test_branches_is_a_broken_input_naming_the_data_file(
    *, tmp_path: Path, branch: bool, contexts: list[str]
) -> None:
    _measure(
        tmp_path,
        source_by_module={"src/pkg/sizes.py": SIZES},
        calls_by_context={
            context: lambda modules: modules["sizes"].is_short(3) for context in contexts
        },
        branch=branch,
    )

    with pytest.raises(
        BrokenInputError, match=f"^{re.escape(_no_per_test_coverage_message(tmp_path))}$"
    ):
        _reader(tmp_path).read_test_coverage_by_module({PurePath("src/pkg/sizes.py"): ()})


def test_an_absent_data_file_is_a_broken_input_naming_it_even_with_no_module_to_read(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        BrokenInputError, match=f"^{re.escape(_no_per_test_coverage_message(tmp_path))}$"
    ):
        _reader(tmp_path).read_test_coverage_by_module({})


def test_a_data_file_that_is_no_coverage_database_is_a_broken_input_naming_it(
    tmp_path: Path,
) -> None:
    (tmp_path / ".coverage").write_text("not a database\n")
    data_file = re.escape(repr(str(tmp_path / ".coverage")))

    with pytest.raises(
        BrokenInputError, match=f"^Couldn't use data file {data_file}: file is not a database$"
    ):
        _reader(tmp_path).read_test_coverage_by_module({PurePath("src/pkg/sizes.py"): ()})
    gc.collect()  # a connection left open warns as it is collected, failing this test


def test_a_coverage_config_coverage_py_refuses_is_a_broken_input_naming_the_pyproject(
    tmp_path: Path,
) -> None:
    _measure(tmp_path, source_by_module={"src/pkg/sizes.py": SIZES}, calls_by_context={})
    reader = _reader(tmp_path, pyproject='[tool.coverage.run]\nbranch = "sometimes"\n')
    pyproject = re.escape(str(tmp_path / "pyproject.toml"))

    with pytest.raises(BrokenInputError, match=f"^Couldn't read config file {pyproject}: "):
        reader.read_test_coverage_by_module({PurePath("src/pkg/sizes.py"): ()})


def test_a_module_that_is_not_python_is_a_broken_input_naming_it(tmp_path: Path) -> None:
    _measure(
        tmp_path,
        source_by_module={"src/pkg/sizes.py": SIZES},
        calls_by_context={
            "tests/test_sizes.py::test_short|run": lambda modules: modules["sizes"].is_short(3)
        },
    )
    (tmp_path / "src/pkg/broken.py").write_text("def is_short(:\n")
    module = re.escape(repr(str(tmp_path / "src/pkg/broken.py")))

    with pytest.raises(BrokenInputError, match=f"^Couldn't parse {module} as Python source: "):
        _reader(tmp_path).read_test_coverage_by_module({PurePath("src/pkg/broken.py"): ()})

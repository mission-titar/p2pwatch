"""The command line, wired to the real check in the given cwd and temporary directory."""

import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
from coverage import Coverage

from coverage_checks.composition.command_line import build_command_line

SIZES = """\
def is_short(size):
    if size < 10:
        return True
    return False
"""


def _measure_sizes(
    package_directory: Path, calls_by_context: dict[str, Callable[[ModuleType], object]]
) -> None:
    """Writes `src/pkg/sizes.py` and records its run as pytest-cov's per-test contexts do."""
    module = package_directory / "src" / "pkg" / "sizes.py"
    module.parent.mkdir(parents=True)
    module.write_text(SIZES)
    (package_directory / "pyproject.toml").write_text('[project]\nname = "pkg"\n')
    coverage = Coverage(
        data_file=str(package_directory / ".coverage"),
        branch=True,
        config_file=False,
        source=[str(package_directory / "src")],
    )
    coverage.start()
    try:
        spec = importlib.util.spec_from_file_location("sizes", module)
        assert spec is not None and spec.loader is not None
        sizes = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sizes)
        for context, call in calls_by_context.items():
            coverage.switch_context(context)
            call(sizes)
    finally:
        coverage.stop()
    coverage.save()


def test_unit_coverage_checks_the_package_in_the_cwd_and_names_it_in_the_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cwd, temporary_directory = tmp_path / "pkg", tmp_path / "tmp"
    (cwd / "tests").mkdir(parents=True)
    (cwd / "tests" / "test_sizes.py").write_text("")
    _measure_sizes(
        cwd,
        {
            "tests/test_sizes.py::test_short|run": lambda sizes: sizes.is_short(3),
            "tests/test_sizes.py::test_long|run": lambda sizes: sizes.is_short(30),
        },
    )
    temporary_directory.mkdir()
    command_line = build_command_line(cwd=cwd, temporary_directory=temporary_directory)

    assert command_line.run(["unit-coverage"]) == 0

    assert capsys.readouterr().out == (
        "pkg: 1 test files map to 1 of 1 modules, 0 are listed without a unit;"
        " 0 of 1 modules short of their own tests\n"
    )
    assert list(temporary_directory.iterdir()) == []  # coverage.py's report gone with its directory


def test_unit_coverage_without_recorded_coverage_names_the_cwd_s_data_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "pkg"\n')
    command_line = build_command_line(cwd=tmp_path, temporary_directory=tmp_path)

    assert command_line.run(["unit-coverage"]) == 1

    assert capsys.readouterr().err.startswith(
        f"no per-test branch coverage in {tmp_path / '.coverage'}: run this package's pytest"
    )

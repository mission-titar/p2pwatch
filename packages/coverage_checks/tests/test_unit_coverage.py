"""Tests for the check that each module's statements and branches are run by its own tests."""

import importlib.util
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace

import pytest
from coverage import Coverage

from coverage_checks.unit_coverage import main

SIZES = """\
LIMIT = 10


def is_short(size):
    if size < LIMIT:
        return True
    return False
"""

OTHER = """\
def run():
    return 1
"""

type Call = Callable[[SimpleNamespace], object]


@pytest.fixture(autouse=True)
def _package_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    Path("pyproject.toml").write_text('[project]\nname = "pkg"\n')


def _write(files_by_path: Mapping[str, str]) -> None:
    for path, text in files_by_path.items():
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(dedent(text))


def _measure(modules: Sequence[str], calls_by_context: Mapping[str, Call]) -> None:
    """Import *modules*, then run each call under its context, as pytest-cov's per-test contexts.

    A call reads each module by its name: `lambda pkg: pkg.sizes.is_short(3)`."""
    coverage = Coverage(branch=True, config_file=False, source=["src"])
    coverage.start()
    try:
        pkg = SimpleNamespace()
        for module in modules:
            spec = importlib.util.spec_from_file_location(Path(module).stem, module)
            assert spec is not None and spec.loader is not None
            pkg.__dict__[spec.name] = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(pkg.__dict__[spec.name])
        for context, call in calls_by_context.items():
            coverage.switch_context(context)
            call(pkg)
    finally:
        coverage.stop()
    coverage.save()


def _main_exit_code() -> object:
    with pytest.raises(SystemExit) as exc_info:
        main()
    return exc_info.value.code


def test_a_module_its_own_tests_run_whole_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write({"src/pkg/sizes.py": SIZES, "tests/test_sizes.py": ""})
    _measure(
        ["src/pkg/sizes.py"],
        {
            "tests/test_sizes.py::test_short|run": lambda pkg: pkg.sizes.is_short(3),
            "tests/test_sizes.py::test_long|run": lambda pkg: pkg.sizes.is_short(30),
        },
    )
    main()
    assert capsys.readouterr().out == (
        f"{tmp_path.name}: 1 test files map to 1 of 1 modules, 0 are listed without a unit;"
        " 0 of 1 modules short of their own tests\n"
    )


def test_what_only_another_module_s_test_runs_fails_naming_the_module(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write({"src/pkg/sizes.py": SIZES, "src/pkg/other.py": OTHER})
    _write({"tests/test_sizes.py": "", "tests/test_other.py": ""})
    _measure(
        ["src/pkg/sizes.py", "src/pkg/other.py"],
        {
            "tests/test_sizes.py::test_short|run": lambda pkg: pkg.sizes.is_short(3),
            "tests/test_other.py::test_run|run": lambda pkg: pkg.other.run(),
            "tests/test_other.py::test_long|setup": lambda pkg: pkg.sizes.is_short(30),
        },
    )
    assert _main_exit_code() == 1
    assert capsys.readouterr().out == (
        "src/pkg/sizes.py: statements 7 and branches 5->7 run by none of its own tests"
        " (tests/test_sizes.py)\n"
        f"{tmp_path.name}: 2 test files map to 2 of 2 modules, 0 are listed without a unit;"
        " 1 of 2 modules short of their own tests\n"
    )


def test_a_function_of_a_module_without_own_tests_is_short(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write({"src/pkg/sizes.py": SIZES, "src/pkg/other.py": OTHER, "tests/test_other.py": ""})
    _measure(
        ["src/pkg/sizes.py", "src/pkg/other.py"],
        {
            "tests/test_other.py::test_short|run": lambda pkg: pkg.sizes.is_short(3),
            "tests/test_other.py::test_long|run": lambda pkg: pkg.sizes.is_short(30),
            "tests/test_other.py::test_run|run": lambda pkg: pkg.other.run(),
        },
    )
    assert _main_exit_code() == 1
    assert capsys.readouterr().out.startswith(
        "src/pkg/sizes.py: statements 5, 6, 7 and branches 5->6, 5->7 run by none of its own"
        " tests (it has none)\n"
    )


def test_what_import_runs_needs_no_own_test(capsys: pytest.CaptureFixture[str]) -> None:
    ports = """\
        from typing import Protocol

        LENGTHS = {}
        for name in ("a", "bb"):
            LENGTHS[name] = len(name)


        class Reader(Protocol):
            def read(self) -> bytes: ...
        """
    _write({"src/pkg/ports.py": ports, "src/pkg/other.py": OTHER, "tests/test_other.py": ""})
    _measure(
        ["src/pkg/ports.py", "src/pkg/other.py"],
        {"tests/test_other.py::test_run|run": lambda pkg: pkg.other.run()},
    )
    main()
    assert "0 of 2 modules short of their own tests" in capsys.readouterr().out


def test_a_top_level_statement_no_test_runs_is_short(capsys: pytest.CaptureFixture[str]) -> None:
    widths = """\
        import sys

        if sys.maxsize > 0:
            WIDTH = 64
        else:
            WIDTH = 32


        def width():
            return WIDTH
        """
    _write({"src/pkg/widths.py": widths, "tests/test_widths.py": ""})
    _measure(
        ["src/pkg/widths.py"],
        {"tests/test_widths.py::test_width|run": lambda pkg: pkg.widths.width()},
    )
    assert _main_exit_code() == 1
    assert capsys.readouterr().out.startswith(
        "src/pkg/widths.py: statements 6 and branches 3->6 run by none of its own tests"
    )


def test_a_branch_to_the_function_s_exit_reads_exit(capsys: pytest.CaptureFixture[str]) -> None:
    names = """\
        def record(names, name):
            if name:
                names.append(name)
        """
    _write({"src/pkg/names.py": names, "tests/test_names.py": ""})
    _measure(
        ["src/pkg/names.py"],
        {"tests/test_names.py::test_record|run": lambda pkg: pkg.names.record([], "a")},
    )
    assert _main_exit_code() == 1
    assert capsys.readouterr().out.startswith(
        "src/pkg/names.py: branches 2->exit run by none of its own tests (tests/test_names.py)\n"
    )


def test_a_test_file_mapping_to_no_module_fails(capsys: pytest.CaptureFixture[str]) -> None:
    _write({"src/pkg/other.py": OTHER, "tests/test_other.py": ""})
    _write({"tests/domain/test_nothing.py": ""})
    _measure(
        ["src/pkg/other.py"], {"tests/test_other.py::test_run|run": lambda pkg: pkg.other.run()}
    )
    assert _main_exit_code() == 1
    assert capsys.readouterr().out.startswith("tests/domain/test_nothing.py: tests no module")


def test_a_test_file_listed_in_the_package_s_pyproject_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    listing = """\
        [tool.coverage_checks.tests_without_unit]
        "tests/test_migration_0002.py" = "its subject is SQL"
        """
    _write({"pyproject.toml": listing, "src/pkg/other.py": OTHER, "tests/test_other.py": ""})
    _write({"tests/test_migration_0002.py": ""})
    _measure(
        ["src/pkg/other.py"], {"tests/test_other.py::test_run|run": lambda pkg: pkg.other.run()}
    )
    main()
    assert capsys.readouterr().out == (
        f"{tmp_path.name}: 1 test files map to 1 of 1 modules, 1 are listed without a unit;"
        " 0 of 1 modules short of their own tests\n"
    )


def test_no_per_test_context_exits_with_how_to_record_them() -> None:
    _write({"src/pkg/sizes.py": SIZES})
    _measure(["src/pkg/sizes.py"], {})
    assert _main_exit_code() == (
        "no per-test branch coverage in .coverage: run this package's pytest first, with branch"
        " coverage and --cov-context=test"
    )


def test_no_coverage_data_exits_with_how_to_record_it() -> None:
    _write({"src/pkg/sizes.py": SIZES})
    assert str(_main_exit_code()).startswith("no per-test branch coverage in .coverage")

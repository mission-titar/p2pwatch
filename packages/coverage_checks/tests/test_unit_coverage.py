"""Tests for the check run in a package's directory: its test files mirror its `src`."""

from collections.abc import Mapping
from pathlib import Path
from textwrap import dedent

import pytest

from coverage_checks.unit_coverage import main


def _write(files_by_path: Mapping[str, str]) -> None:
    for path, text in files_by_path.items():
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(dedent(text))


@pytest.fixture(autouse=True)
def _package_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write({"pyproject.toml": '[project]\nname = "pkg"\n', "src/pkg/sizes.py": ""})
    _write({"src/pkg/other.py": "", "tests/test_sizes.py": ""})


def test_test_files_mirroring_src_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main()
    assert capsys.readouterr().out == (
        f"{tmp_path.name}: 1 test files map to 1 of 2 modules, 0 are listed without a unit\n"
    )


def test_a_test_file_mapping_to_no_module_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write({"tests/domain/test_nothing.py": ""})
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
    assert capsys.readouterr().out == (
        "tests/domain/test_nothing.py: tests no module of src; name it after the module it tests,"
        " or list it in [tool.coverage_checks] tests_without_unit with its reason\n"
        f"{tmp_path.name}: 1 test files map to 1 of 2 modules, 0 are listed without a unit\n"
    )


def test_a_test_file_listed_in_the_package_s_pyproject_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    listing = """\
        [tool.coverage_checks.tests_without_unit]
        "tests/domain/test_nothing.py" = "seeded"
        """
    _write({"pyproject.toml": listing, "tests/domain/test_nothing.py": ""})
    main()
    assert capsys.readouterr().out == (
        f"{tmp_path.name}: 1 test files map to 1 of 2 modules, 1 are listed without a unit\n"
    )

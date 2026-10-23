"""The check, wired to the real readers, its report directory held for one check."""

from pathlib import Path

import pytest

from coverage_checks.composition.unit_coverage_composition import UnitCoverageComposition
from coverage_checks.domain.broken_input_error import BrokenInputError


def _checker(package_directory: Path, temporary_directory: Path) -> UnitCoverageComposition:
    (package_directory / "pyproject.toml").write_text('[project]\nname = "pkg"\n')
    return UnitCoverageComposition(
        package_directory=package_directory,
        data_file=package_directory / ".coverage",
        temporary_directory=temporary_directory,
    )


def test_check_leaves_the_temporary_directory_as_it_found_it_even_when_it_raises(
    tmp_path: Path,
) -> None:
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "sizes.py").write_text("LIMIT = 10\n")
    temporary_directory = tmp_path / "tmp"
    temporary_directory.mkdir()

    with pytest.raises(BrokenInputError):
        _checker(tmp_path, temporary_directory).check_unit_coverage()

    assert list(temporary_directory.iterdir()) == []


def test_check_makes_its_report_directory_in_the_temporary_directory(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError) as raised:
        _checker(tmp_path, tmp_path / "absent").check_unit_coverage()

    assert Path(raised.value.filename).parent == tmp_path / "absent"

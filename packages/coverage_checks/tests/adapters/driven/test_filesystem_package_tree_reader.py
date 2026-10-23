import re
from pathlib import Path, PurePath

import pytest

from coverage_checks.adapters.driven.filesystem_package_tree_reader import (
    FilesystemPackageTreeReader,
)
from coverage_checks.domain.broken_input_error import BrokenInputError


def _touch(package_directory: Path, *paths: str) -> None:
    for path in paths:
        (package_directory / path).parent.mkdir(parents=True, exist_ok=True)
        (package_directory / path).touch()


def test_read_package_tree_lists_the_modules_and_the_test_files_under_the_directory(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "pkg"\n')
    _touch(tmp_path, "src/pkg/__init__.py", "src/pkg/a/b.py", "src/pkg/a/data.txt", "src/top.py")
    _touch(tmp_path, "tests/test_init.py", "tests/a/test_b.py", "tests/a/conftest.py")

    package_tree = FilesystemPackageTreeReader(package_directory=tmp_path).read_package_tree()

    assert sorted(package_tree.modules) == [
        PurePath("src/pkg/__init__.py"),
        PurePath("src/pkg/a/b.py"),
    ]
    assert sorted(package_tree.test_files) == [
        PurePath("tests/a/test_b.py"),
        PurePath("tests/test_init.py"),
    ]
    assert package_tree.tests_without_unit == {}


def test_read_package_tree_reads_tests_without_unit_from_the_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.coverage_checks.tests_without_unit]\n"
        '"tests/test_migration_0002.py" = "its subject is SQL"\n'
        '"tests/integration/" = 3\n'
    )

    package_tree = FilesystemPackageTreeReader(package_directory=tmp_path).read_package_tree()

    assert package_tree.tests_without_unit == {
        "tests/test_migration_0002.py": "its subject is SQL",
        "tests/integration/": 3,
    }


def test_read_module_source_reads_a_module_under_the_directory(tmp_path: Path) -> None:
    (tmp_path / "src/pkg").mkdir(parents=True)
    (tmp_path / "src/pkg/sizes.py").write_text("LIMIT = 10  # « pas plus »\n", encoding="utf-8")

    reader = FilesystemPackageTreeReader(package_directory=tmp_path)

    assert reader.read_module_source(PurePath("src/pkg/sizes.py")) == "LIMIT = 10  # « pas plus »\n"


def test_read_package_tree_without_a_pyproject_raises_a_broken_input_naming_it(
    tmp_path: Path,
) -> None:
    pyproject = re.escape(str(tmp_path / "pyproject.toml"))

    with pytest.raises(BrokenInputError, match=f"^{pyproject}: No such file or directory$"):
        FilesystemPackageTreeReader(package_directory=tmp_path).read_package_tree()


def test_read_package_tree_of_a_pyproject_not_in_utf_8_raises_a_broken_input_naming_it(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_bytes('[project]\nname = "é"\n'.encode("latin-1"))
    pyproject = re.escape(str(tmp_path / "pyproject.toml"))

    with pytest.raises(BrokenInputError, match=f"^{pyproject}: not UTF-8$"):
        FilesystemPackageTreeReader(package_directory=tmp_path).read_package_tree()


def test_read_package_tree_of_a_pyproject_not_in_toml_raises_a_broken_input_naming_it(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project\n")
    pyproject = re.escape(str(tmp_path / "pyproject.toml"))

    with pytest.raises(
        BrokenInputError, match=f"^{pyproject}: Expected ']' at the end of a table declaration "
    ):
        FilesystemPackageTreeReader(package_directory=tmp_path).read_package_tree()


def test_read_module_source_of_an_absent_module_raises_a_broken_input_naming_it(
    tmp_path: Path,
) -> None:
    module = re.escape(str(tmp_path / "src/pkg/sizes.py"))

    with pytest.raises(BrokenInputError, match=f"^{module}: No such file or directory$"):
        FilesystemPackageTreeReader(package_directory=tmp_path).read_module_source(
            PurePath("src/pkg/sizes.py")
        )

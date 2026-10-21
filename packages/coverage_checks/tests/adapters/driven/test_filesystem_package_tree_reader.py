from pathlib import Path, PurePath

from coverage_checks.adapters.driven.filesystem_package_tree_reader import (
    FilesystemPackageTreeReader,
)


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

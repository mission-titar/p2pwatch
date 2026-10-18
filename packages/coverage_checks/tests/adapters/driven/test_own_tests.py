"""Tests for a module's own tests, and for the test files listed without a unit."""

from pathlib import Path

import pytest

from coverage_checks.adapters.driven.own_tests import find_own_tests


@pytest.fixture(autouse=True)
def _package_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def _touch(*paths: str) -> None:
    for path in paths:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).touch()


def test_a_test_file_mirroring_a_module_is_its_own() -> None:
    _touch("src/pkg/__init__.py", "src/pkg/a/b.py", "tests/a/test_b.py", "tests/a/conftest.py")
    own_tests = find_own_tests({})
    assert own_tests.test_files_by_module == {
        Path("src/pkg/__init__.py"): (),
        Path("src/pkg/a/b.py"): (Path("tests/a/test_b.py"),),
    }
    assert (own_tests.mapped_test_count, own_tests.listed_test_count) == (1, 0)
    assert own_tests.problems == ()


def test_an_aspect_file_belongs_to_the_longest_module_name_it_extends() -> None:
    _touch("src/pkg/b.py", "src/pkg/b_c.py", "tests/test_b_errors.py", "tests/test_b_c_more.py")
    assert find_own_tests({}).test_files_by_module == {
        Path("src/pkg/b.py"): (Path("tests/test_b_errors.py"),),
        Path("src/pkg/b_c.py"): (Path("tests/test_b_c_more.py"),),
    }


def test_a_dunder_module_drops_its_underscores() -> None:
    _touch("src/pkg/__main__.py", "src/pkg/a/__init__.py", "tests/test_main.py")
    _touch("tests/a/test_init_exports.py")
    assert find_own_tests({}).test_files_by_module == {
        Path("src/pkg/__main__.py"): (Path("tests/test_main.py"),),
        Path("src/pkg/a/__init__.py"): (Path("tests/a/test_init_exports.py"),),
    }


@pytest.mark.parametrize(
    "test_file", ["tests/test_b.py", "tests/a/test_bb.py", "tests/a/test_c.py"]
)
def test_a_test_file_mapping_to_no_module_fails(test_file: str) -> None:
    _touch("src/pkg/a/b.py", test_file)
    own_tests = find_own_tests({})
    assert own_tests.problems == (
        f"{test_file}: tests no module of src; name it after the module it tests, or list it in"
        " [tool.coverage_checks] tests_without_unit with its reason",
    )
    assert own_tests.mapped_test_count == 0


def test_a_listed_test_file_passes_unmapped() -> None:
    _touch("src/pkg/b.py", "tests/test_migration_0002.py")
    own_tests = find_own_tests({"tests/test_migration_0002.py": "its subject is SQL"})
    assert own_tests.test_files_by_module == {Path("src/pkg/b.py"): ()}
    assert (own_tests.mapped_test_count, own_tests.listed_test_count) == (0, 1)
    assert own_tests.problems == ()


def test_a_listed_directory_lists_every_test_file_under_it() -> None:
    _touch("src/pkg/b.py", "tests/integration/test_loop.py", "tests/integration/x/test_api.py")
    own_tests = find_own_tests({"tests/integration/": "integration suites, deselected by marker"})
    assert own_tests.listed_test_count == 2
    assert own_tests.problems == ()


def test_a_listed_test_file_that_tests_a_module_fails() -> None:
    _touch("src/pkg/b.py", "tests/test_b.py")
    own_tests = find_own_tests({"tests/test_b.py": "listed by mistake"})
    assert own_tests.problems == (
        "tests/test_b.py: listed in tests_without_unit, but tests src/pkg/b.py",
    )
    assert own_tests.test_files_by_module == {Path("src/pkg/b.py"): ()}


@pytest.mark.parametrize("listed_path", ["tests/test_gone.py", "tests/gone/"])
def test_an_entry_listing_no_test_file_fails(listed_path: str) -> None:
    _touch("src/pkg/b.py", "tests/test_b.py")
    assert find_own_tests({listed_path: "its file was deleted"}).problems == (
        f"{listed_path}: listed in tests_without_unit, but names no test file",
    )


@pytest.mark.parametrize("reason", ["", "  ", 3])
def test_an_entry_without_its_reason_fails(reason: object) -> None:
    _touch("tests/test_migration_0002.py")
    assert find_own_tests({"tests/test_migration_0002.py": reason}).problems == (
        "tests/test_migration_0002.py: listed in tests_without_unit without its reason",
    )


@pytest.mark.parametrize("stem", ["main", "init"])
def test_a_module_named_like_a_dunder_beside_it_fails(stem: str) -> None:
    _touch(f"src/pkg/__{stem}__.py", f"src/pkg/{stem}.py")
    assert find_own_tests({}).problems == (
        f"src/pkg/{stem}.py: its tests would be named like those of __{stem}__.py beside it;"
        " rename it",
    )


def test_a_module_named_main_without_a_dunder_beside_it_is_tested_by_test_main() -> None:
    _touch("src/pkg/__init__.py", "src/pkg/a/main.py", "tests/a/test_main.py")
    own_tests = find_own_tests({})
    assert own_tests.test_files_by_module[Path("src/pkg/a/main.py")] == (
        Path("tests/a/test_main.py"),
    )
    assert own_tests.problems == ()

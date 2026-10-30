"""Tests for a module's own tests, and for the test files listed without a unit."""

from collections.abc import Mapping
from pathlib import PurePath

import pytest

from coverage_checks.domain.own_tests import (
    ListedTestOfModule,
    ListingWithoutReason,
    StaleListing,
    UnitNameCollision,
    UnmappedTestFile,
    find_own_tests,
)
from coverage_checks.domain.package_tree import PackageTree


def _tree(*paths: str, tests_without_unit: Mapping[str, object] | None = None) -> PackageTree:
    return PackageTree(
        modules=tuple(PurePath(path) for path in paths if path.startswith("src/")),
        test_files=tuple(PurePath(path) for path in paths if path.startswith("tests/")),
        tests_without_unit=tests_without_unit or {},
    )


def test_a_test_file_mirroring_a_module_is_its_own() -> None:
    own_tests = find_own_tests(_tree("src/pkg/__init__.py", "src/pkg/a/b.py", "tests/a/test_b.py"))
    assert own_tests.test_files_by_module == {
        PurePath("src/pkg/__init__.py"): (),
        PurePath("src/pkg/a/b.py"): (PurePath("tests/a/test_b.py"),),
    }
    assert (own_tests.mapped_test_count, own_tests.listed_test_count) == (1, 0)
    assert own_tests.problems == ()


def test_modules_and_test_files_are_mapped_in_path_order() -> None:
    own_tests = find_own_tests(
        _tree("src/pkg/c.py", "src/pkg/b.py", "tests/test_b_more.py", "tests/test_b.py")
    )
    assert list(own_tests.test_files_by_module.items()) == [
        (PurePath("src/pkg/b.py"), (PurePath("tests/test_b.py"), PurePath("tests/test_b_more.py"))),
        (PurePath("src/pkg/c.py"), ()),
    ]


def test_an_aspect_file_belongs_to_the_longest_module_name_it_extends() -> None:
    own_tests = find_own_tests(
        _tree("src/pkg/b.py", "src/pkg/b_c.py", "tests/test_b_errors.py", "tests/test_b_c_more.py")
    )
    assert own_tests.test_files_by_module == {
        PurePath("src/pkg/b.py"): (PurePath("tests/test_b_errors.py"),),
        PurePath("src/pkg/b_c.py"): (PurePath("tests/test_b_c_more.py"),),
    }


def test_a_dunder_module_drops_its_underscores() -> None:
    own_tests = find_own_tests(
        _tree(
            "src/pkg/__main__.py",
            "src/pkg/a/__init__.py",
            "tests/test_main.py",
            "tests/a/test_init_exports.py",
        )
    )
    assert own_tests.test_files_by_module == {
        PurePath("src/pkg/__main__.py"): (PurePath("tests/test_main.py"),),
        PurePath("src/pkg/a/__init__.py"): (PurePath("tests/a/test_init_exports.py"),),
    }


@pytest.mark.parametrize(
    "test_file", ["tests/test_b.py", "tests/a/test_bb.py", "tests/a/test_c.py"]
)
def test_a_test_file_mapping_to_no_module_fails(test_file: str) -> None:
    own_tests = find_own_tests(_tree("src/pkg/a/b.py", test_file))
    assert own_tests.problems == (UnmappedTestFile(test_file=PurePath(test_file)),)
    assert own_tests.mapped_test_count == 0


def test_a_listed_test_file_passes_unmapped() -> None:
    own_tests = find_own_tests(
        _tree(
            "src/pkg/b.py",
            "tests/test_migration_0002.py",
            tests_without_unit={"tests/test_migration_0002.py": "its subject is SQL"},
        )
    )
    assert own_tests.test_files_by_module == {PurePath("src/pkg/b.py"): ()}
    assert (own_tests.mapped_test_count, own_tests.listed_test_count) == (0, 1)
    assert own_tests.problems == ()


def test_a_listed_directory_lists_every_test_file_under_it() -> None:
    own_tests = find_own_tests(
        _tree(
            "src/pkg/b.py",
            "tests/integration/test_loop.py",
            "tests/integration/x/test_api.py",
            tests_without_unit={"tests/integration/": "integration suites, deselected by marker"},
        )
    )
    assert own_tests.listed_test_count == 2
    assert own_tests.problems == ()


def test_a_listed_test_file_that_tests_a_module_fails() -> None:
    own_tests = find_own_tests(
        _tree("src/pkg/b.py", "tests/test_b.py", tests_without_unit={"tests/test_b.py": "listed"})
    )
    assert own_tests.problems == (
        ListedTestOfModule(test_file=PurePath("tests/test_b.py"), module=PurePath("src/pkg/b.py")),
    )
    assert own_tests.test_files_by_module == {PurePath("src/pkg/b.py"): ()}


@pytest.mark.parametrize("listed_path", ["tests/test_gone.py", "tests/gone/"])
def test_an_entry_listing_no_test_file_fails(listed_path: str) -> None:
    own_tests = find_own_tests(
        _tree("src/pkg/b.py", "tests/test_b.py", tests_without_unit={listed_path: "deleted"})
    )
    assert own_tests.problems == (StaleListing(listed_path=listed_path),)


@pytest.mark.parametrize("reason", ["", "  ", 3])
def test_an_entry_without_its_reason_fails(reason: object) -> None:
    own_tests = find_own_tests(
        _tree(
            "tests/test_migration_0002.py",
            tests_without_unit={"tests/test_migration_0002.py": reason},
        )
    )
    assert own_tests.problems == (ListingWithoutReason(listed_path="tests/test_migration_0002.py"),)


@pytest.mark.parametrize("stem", ["main", "init"])
def test_a_module_named_like_a_dunder_beside_it_fails(stem: str) -> None:
    assert find_own_tests(_tree(f"src/pkg/__{stem}__.py", f"src/pkg/{stem}.py")).problems == (
        UnitNameCollision(module=PurePath(f"src/pkg/{stem}.py")),
    )


def test_a_module_named_main_without_a_dunder_beside_it_is_tested_by_test_main() -> None:
    own_tests = find_own_tests(
        _tree("src/pkg/__init__.py", "src/pkg/a/main.py", "tests/a/test_main.py")
    )
    assert own_tests.test_files_by_module[PurePath("src/pkg/a/main.py")] == (
        PurePath("tests/a/test_main.py"),
    )
    assert own_tests.problems == ()

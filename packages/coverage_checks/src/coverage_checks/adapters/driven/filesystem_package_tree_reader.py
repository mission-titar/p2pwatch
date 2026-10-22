import tomllib
from pathlib import Path, PurePath

from coverage_checks.application.ports.driven.package_tree_reader import PackageTreeReader
from coverage_checks.domain.package_tree import PackageTree


class FilesystemPackageTreeReader(PackageTreeReader):
    """A package's directory: `src/*/**/*.py`, `tests/**/test_*.py` and `pyproject.toml`."""

    def __init__(self, *, package_directory: Path) -> None:
        self._package_directory = package_directory

    def read_package_tree(self) -> PackageTree:
        pyproject = tomllib.loads(
            (self._package_directory / "pyproject.toml").read_text(encoding="utf-8")
        )
        tests_without_unit: dict[str, object] = (
            pyproject.get("tool", {}).get("coverage_checks", {}).get("tests_without_unit", {})
        )
        return PackageTree(
            modules=self._list("src/*/**/*.py"),
            test_files=self._list("tests/**/test_*.py"),
            tests_without_unit=tests_without_unit,
        )

    def read_module_source(self, module: PurePath) -> str:
        return (self._package_directory / module).read_text(encoding="utf-8")

    def _list(self, pattern: str) -> tuple[PurePath, ...]:
        return tuple(
            path.relative_to(self._package_directory)
            for path in self._package_directory.glob(pattern)
        )

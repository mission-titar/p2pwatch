from abc import ABC, abstractmethod
from pathlib import PurePath

from coverage_checks.domain.package_tree import PackageTree


class PackageTreeReader(ABC):
    """Reads a package's tree: its modules and their source, its test files and those it lists
    without a unit."""

    @abstractmethod
    def read_package_tree(self) -> PackageTree:
        """The package's modules and test files, and its `tests_without_unit`."""

    @abstractmethod
    def read_module_source(self, module: PurePath) -> str:
        """The source of *module*, one of the tree's."""

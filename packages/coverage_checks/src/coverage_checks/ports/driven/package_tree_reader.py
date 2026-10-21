from abc import ABC, abstractmethod

from coverage_checks.domain.package_tree import PackageTree


class PackageTreeReader(ABC):
    """Reads a package's tree: its modules, its test files and those it lists without a unit."""

    @abstractmethod
    def read_package_tree(self) -> PackageTree:
        """The package's modules and test files, and its `tests_without_unit`."""

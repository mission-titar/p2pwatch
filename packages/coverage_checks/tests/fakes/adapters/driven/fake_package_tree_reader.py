from collections.abc import Mapping
from pathlib import PurePath

from coverage_checks.application.ports.driven.package_tree_reader import PackageTreeReader
from coverage_checks.domain.package_tree import PackageTree


class FakePackageTreeReader(PackageTreeReader):
    """Reads the tree it is given, and each module's source from ``sources_by_module``."""

    def __init__(
        self, package_tree: PackageTree, *, sources_by_module: Mapping[PurePath, str]
    ) -> None:
        self._package_tree = package_tree
        self._sources_by_module = sources_by_module

    def read_package_tree(self) -> PackageTree:
        return self._package_tree

    def read_module_source(self, module: PurePath) -> str:
        return self._sources_by_module[module]

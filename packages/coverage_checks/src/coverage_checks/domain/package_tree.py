from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePath


@dataclass(kw_only=True, frozen=True)
class PackageTree:
    """A package's modules and test files, relative to its directory, and its `tests_without_unit`.

    `tests_without_unit` maps a test file, or a directory ending in `/`, to its reason as read."""

    modules: tuple[PurePath, ...]
    test_files: tuple[PurePath, ...]
    tests_without_unit: Mapping[str, object]

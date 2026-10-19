"""``CoverageReader``: reads what the targets' coverage is computed from."""

from abc import ABC, abstractmethod
from collections.abc import Mapping


class CoverageReader(ABC):
    """Reads the catalog from any thread."""

    @abstractmethod
    def read_target_coverage(self) -> Mapping[str, tuple[str, ...]]:
        """By ``target_id``, the tier of each file's latest decision for it, none retracted."""

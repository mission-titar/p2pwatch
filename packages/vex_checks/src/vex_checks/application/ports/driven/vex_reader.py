from abc import ABC, abstractmethod
from pathlib import PurePath


class VexReader(ABC):
    """Reads an OpenVEX document's claims."""

    @abstractmethod
    def read_claims(self, vex_path: PurePath) -> dict[str, str]:
        """The justification of each ``not_affected`` statement, by advisory id."""

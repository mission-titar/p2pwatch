"""The fingerprint of the policy the catalog was last re-evaluated against, in ``local.db``.

``local.db`` is NEVER merged: these ports do not cross the node boundary (invariant MVP §11).
"""

from abc import ABC, abstractmethod


class PolicyFingerprintReader(ABC):
    """Reads the fingerprint the latest re-evaluation stored."""

    @abstractmethod
    def read_policy_fingerprint(self) -> str | None:
        """The stored fingerprint, ``None`` before the first re-evaluation."""


class PolicyFingerprintWriter(ABC):
    """Stores the fingerprint of the policy the catalog was re-evaluated against."""

    @abstractmethod
    def set_policy_fingerprint(self, fingerprint: str) -> None:
        """Replaces the stored fingerprint with ``fingerprint``."""

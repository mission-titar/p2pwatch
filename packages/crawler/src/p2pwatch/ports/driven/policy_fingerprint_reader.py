"""``PolicyFingerprintReader``: the fingerprint of the policy the catalog was last
re-evaluated against, in ``local.db``, never merged (invariant MVP §11)."""

from abc import ABC, abstractmethod


class PolicyFingerprintReader(ABC):
    """Reads the fingerprint the latest re-evaluation stored."""

    @abstractmethod
    def read_policy_fingerprint(self) -> str | None:
        """The stored fingerprint, ``None`` before the first re-evaluation."""

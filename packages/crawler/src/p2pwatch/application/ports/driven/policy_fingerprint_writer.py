"""``PolicyFingerprintWriter``: the fingerprint of the policy the catalog was last
re-evaluated against, in ``local.db``, never merged (invariant MVP §11)."""

from abc import ABC, abstractmethod


class PolicyFingerprintWriter(ABC):
    """Stores the fingerprint of the policy the catalog was re-evaluated against."""

    @abstractmethod
    def set_policy_fingerprint(self, fingerprint: str) -> None:
        """Replaces the stored fingerprint with ``fingerprint``."""

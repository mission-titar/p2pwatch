"""``LocalStateRepository`` port: the re-evaluation marker (spec data-model §4/§6).

SYNCHRONOUS Protocol (same principle as ``CatalogRepository``). ``local.db`` is NEVER merged:
this port does not cross the node boundary (invariant MVP §11).
"""

from typing import Protocol


class LocalStateRepository(Protocol):
    """Sync local-state contract: the reevaluated policy fingerprint."""

    def reevaluated_policy_fingerprint(self) -> str | None: ...

    def set_reevaluated_policy_fingerprint(self, fingerprint: str) -> None: ...

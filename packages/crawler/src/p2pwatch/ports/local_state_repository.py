"""``LocalStateRepository`` port: node identity + re-evaluation marker (spec data-model §4/§6).

SYNCHRONOUS Protocol (same principle as ``CatalogRepository``). ``local.db`` is NEVER merged:
this port does not cross the node boundary (invariant MVP §11).
"""

from typing import Protocol


class LocalStateRepository(Protocol):
    """Sync local-state contract: stable node identity + reevaluated policy fingerprint."""

    def get_or_create_node_id(self) -> str: ...

    def reevaluated_policy_fingerprint(self) -> str | None: ...

    def set_reevaluated_policy_fingerprint(self, fingerprint: str) -> None: ...

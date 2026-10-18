from datetime import UTC, datetime

from p2pwatch.ports.driven.local_state_repository import LocalStateRepository


class _StubRepository:
    """Minimal structural implementation: satisfies LocalStateRepository WITHOUT importing it."""

    def __init__(self) -> None:
        self.created_at: list[datetime] = []

    def get_or_create_node_id(self, created_at: datetime) -> str:
        self.created_at.append(created_at)
        return "00000000-0000-0000-0000-000000000000"

    def reevaluated_policy_fingerprint(self) -> str | None:
        return None

    def set_reevaluated_policy_fingerprint(self, fingerprint: str) -> None:
        return None


def test_protocol_is_satisfied_structurally() -> None:
    stub = _StubRepository()
    repository: LocalStateRepository = stub  # mypy proves the satisfaction
    created_at = datetime(2026, 6, 12, tzinfo=UTC)
    assert repository.get_or_create_node_id(created_at) == "00000000-0000-0000-0000-000000000000"
    assert stub.created_at == [created_at]
    assert repository.reevaluated_policy_fingerprint() is None
    repository.set_reevaluated_policy_fingerprint("abc")

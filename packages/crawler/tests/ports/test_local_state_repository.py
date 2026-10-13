from p2pwatch.ports.local_state_repository import LocalStateRepository


class _StubRepository:
    """Minimal structural implementation: satisfies LocalStateRepository WITHOUT importing it."""

    def get_or_create_node_id(self) -> str:
        return "00000000-0000-0000-0000-000000000000"

    def reevaluated_policy_fingerprint(self) -> str | None:
        return None

    def set_reevaluated_policy_fingerprint(self, fingerprint: str) -> None:
        return None


def test_protocol_is_satisfied_structurally() -> None:
    repository: LocalStateRepository = _StubRepository()  # mypy proves the satisfaction
    assert repository.get_or_create_node_id() == "00000000-0000-0000-0000-000000000000"
    assert repository.reevaluated_policy_fingerprint() is None
    repository.set_reevaluated_policy_fingerprint("abc")

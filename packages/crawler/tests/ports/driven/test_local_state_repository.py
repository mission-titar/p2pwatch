from p2pwatch.ports.driven.local_state_repository import LocalStateRepository


class _StubRepository:
    """Minimal structural implementation: satisfies LocalStateRepository WITHOUT importing it."""

    def __init__(self) -> None:
        self.fingerprints: list[str] = []

    def reevaluated_policy_fingerprint(self) -> str | None:
        return None

    def set_reevaluated_policy_fingerprint(self, fingerprint: str) -> None:
        self.fingerprints.append(fingerprint)


def test_protocol_is_satisfied_structurally() -> None:
    stub = _StubRepository()
    repository: LocalStateRepository = stub  # mypy proves the satisfaction
    assert repository.reevaluated_policy_fingerprint() is None
    repository.set_reevaluated_policy_fingerprint("abc")
    assert stub.fingerprints == ["abc"]

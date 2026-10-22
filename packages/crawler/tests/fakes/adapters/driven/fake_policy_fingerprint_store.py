from p2pwatch.application.ports.driven.policy_fingerprint_reader import PolicyFingerprintReader
from p2pwatch.application.ports.driven.policy_fingerprint_writer import PolicyFingerprintWriter


class FakePolicyFingerprintStore(PolicyFingerprintReader, PolicyFingerprintWriter):
    """Keeps the fingerprint it is given, and each one set."""

    def __init__(self, *, stored_fingerprint: str | None) -> None:
        self.stored_fingerprint = stored_fingerprint
        self.set_calls: list[str] = []

    def read_policy_fingerprint(self) -> str | None:
        return self.stored_fingerprint

    def set_policy_fingerprint(self, fingerprint: str) -> None:
        self.set_calls.append(fingerprint)
        self.stored_fingerprint = fingerprint

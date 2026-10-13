from p2pwatch.ports.wake_hub import WakeHub


class _StubWakeHub:
    """Satisfies WakeHub structurally (without importing it)."""

    def __init__(self) -> None:
        self.woken_subjects: list[str] = []

    def wake(self, subject: str) -> None:
        self.woken_subjects.append(subject)

    async def wait(self, subject: str) -> None:
        return None


def test_protocol_is_satisfied_structurally() -> None:
    hub: WakeHub = _StubWakeHub()
    hub.wake("062A")
    assert isinstance(hub, _StubWakeHub)
    assert hub.woken_subjects == ["062A"]

from p2pwatch.ports.rng import Rng


class _StubRng:
    def jitter(self, span: float) -> float:
        return 0.0


def test_rng_protocol_is_satisfied_structurally() -> None:
    rng: Rng = _StubRng()
    assert rng.jitter(5.0) == 0.0

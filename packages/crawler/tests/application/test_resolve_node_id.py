"""The node's id: the configured one wins, else the one ``local.db`` holds."""

from datetime import UTC, datetime

from p2pwatch.application.resolve_node_id import resolve_node_id
from p2pwatch_testing.application.fakes import FakeTime


class _FakeLocalState:
    """Records each creation instant it is given; only the node id matters here."""

    def __init__(self) -> None:
        self.created_at: list[datetime] = []

    def get_or_create_node_id(self, created_at: datetime) -> str:
        self.created_at.append(created_at)
        return "stored-node"

    def reevaluated_policy_fingerprint(self) -> str | None:
        return None

    def set_reevaluated_policy_fingerprint(self, fingerprint: str) -> None:
        return None


def test_the_configured_node_id_wins_and_creates_none() -> None:
    local_state = _FakeLocalState()

    node_id = resolve_node_id("forced-node", local_state, FakeTime().wall)

    assert node_id == "forced-node"
    assert local_state.created_at == []


def test_without_a_configured_one_the_stored_node_id_is_read_at_the_wall_clock_now() -> None:
    local_state = _FakeLocalState()
    fake_time = FakeTime(datetime(2026, 10, 18, 9, 30, tzinfo=UTC))

    node_id = resolve_node_id(None, local_state, fake_time.wall)

    assert node_id == "stored-node"
    assert local_state.created_at == [datetime(2026, 10, 18, 9, 30, tzinfo=UTC)]

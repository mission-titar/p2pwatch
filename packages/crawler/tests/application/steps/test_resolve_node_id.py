"""The node's id: the configured one wins, else the one ``local.db`` holds, else a new one."""

from datetime import UTC, datetime

from p2pwatch.application.steps.resolve_node_id import resolve_node_id
from tests.fakes.application.fakes import FakeNodeIdGenerator, FakeNodeIdStore, FakeTime


def _resolve(
    configured_node_id: str | None,
    store: FakeNodeIdStore,
    fake_time: FakeTime | None = None,
) -> str:
    return resolve_node_id(
        configured_node_id,
        node_id_reader=store,
        node_id_writer=store,
        node_id_generator=FakeNodeIdGenerator("new-node"),
        wall_clock=(fake_time or FakeTime()).wall,
    )


def test_the_configured_node_id_wins_and_neither_reads_nor_records_one() -> None:
    store = FakeNodeIdStore(stored_node_id="stored-node")

    assert _resolve("forced-node", store) == "forced-node"
    assert store.reads == 0
    assert store.recorded == []


def test_without_a_configured_one_the_stored_node_id_is_kept() -> None:
    store = FakeNodeIdStore(stored_node_id="stored-node")

    assert _resolve(None, store) == "stored-node"
    assert store.recorded == []


def test_without_a_stored_one_a_new_node_id_is_recorded_at_the_wall_clock_now() -> None:
    store = FakeNodeIdStore(stored_node_id=None)
    fake_time = FakeTime(datetime(2026, 10, 18, 9, 30, tzinfo=UTC))

    assert _resolve(None, store, fake_time) == "new-node"
    assert store.recorded == [("new-node", datetime(2026, 10, 18, 9, 30, tzinfo=UTC))]

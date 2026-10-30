"""The node's id: the one ``local.db`` holds, else a new one."""

from datetime import UTC, datetime

from p2pwatch.application.steps.node_id_resolver import NodeIdResolver
from p2pwatch.domain.identifiers import NodeId
from tests.fakes.adapters.driven.fake_node_id_generator import FakeNodeIdGenerator
from tests.fakes.adapters.driven.fake_node_id_store import FakeNodeIdStore
from tests.fakes.adapters.driven.fake_time import FakeTime


def _resolve(store: FakeNodeIdStore, *, fake_time: FakeTime | None = None) -> NodeId:
    return NodeIdResolver(
        node_id_reader=store,
        node_id_writer=store,
        node_id_generator=FakeNodeIdGenerator(NodeId("new-node")),
        wall_clock=(fake_time or FakeTime()).wall,
    ).resolve()


def test_the_stored_node_id_is_kept() -> None:
    store = FakeNodeIdStore(stored_node_id=NodeId("stored-node"))

    assert _resolve(store) == "stored-node"
    assert store.recorded == []


def test_without_a_stored_one_a_new_node_id_is_recorded_at_the_wall_clock_now() -> None:
    store = FakeNodeIdStore(stored_node_id=None)
    fake_time = FakeTime(datetime(2026, 10, 18, 9, 30, tzinfo=UTC))

    assert _resolve(store, fake_time=fake_time) == "new-node"
    assert store.recorded == [("new-node", datetime(2026, 10, 18, 9, 30, tzinfo=UTC))]

"""``DescribeNode``: the node's state, as local.db holds it, and the alerts kept open."""

from datetime import UTC, datetime, timedelta

import pytest

from p2pwatch.adapters.driven.in_memory_open_alert_store import InMemoryOpenAlertStore
from p2pwatch.application.ports.driving.node_describer import NodeDescription
from p2pwatch.application.use_cases.describe_node import DescribeNode
from p2pwatch.domain.health.open_alert import OpenAlert
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.node_state import NodeState
from tests.fakes.adapters.driven.fake_node_state_reader import FakeNodeStateReader
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.support.application.steps.node_health import build_node_health
from tests.support.domain.health_alerts import UNREACHABLE, UNREPAIRED

_NODE_STATE = NodeState(
    node_id=NodeId("node-1"),
    created_at=datetime(2026, 6, 1, tzinfo=UTC),
    downloads=(),
    backoff_state_by_key={},
)


def test_describing_the_node_returns_the_state_it_reads() -> None:
    description = DescribeNode(
        node_state_reader=FakeNodeStateReader(_NODE_STATE),
        open_alert_reader=InMemoryOpenAlertStore(),
    ).describe_node()

    assert description == NodeDescription(node_state=_NODE_STATE, open_alerts=())


@pytest.mark.asyncio
async def test_describing_the_node_returns_the_alerts_its_health_keeps_open_since_each_opened() -> (
    None
):
    fake_time, open_alert_store = FakeTime(), InMemoryOpenAlertStore()
    node_health = build_node_health(open_alert_writer=open_alert_store, wall_clock=fake_time.wall)
    await node_health.open_alert(UNREACHABLE.alert)
    fake_time.advance(timedelta(minutes=15))
    await node_health.open_alert(UNREPAIRED.alert)

    description = DescribeNode(
        node_state_reader=FakeNodeStateReader(_NODE_STATE), open_alert_reader=open_alert_store
    ).describe_node()

    opened_at = datetime(2026, 6, 12, tzinfo=UTC)
    assert description.open_alerts == (
        OpenAlert(alert=UNREACHABLE.alert, opened_at=opened_at),
        OpenAlert(alert=UNREPAIRED.alert, opened_at=opened_at + timedelta(minutes=15)),
    )

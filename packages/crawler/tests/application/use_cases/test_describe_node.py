"""``DescribeNode``: the node's state, as local.db holds it."""

from datetime import UTC, datetime

from p2pwatch.application.ports.driving.node_describer import NodeDescription
from p2pwatch.application.use_cases.describe_node import DescribeNode
from p2pwatch.domain.node_state import NodeState
from tests.fakes.adapters.driven.fake_node_state_reader import FakeNodeStateReader


def test_describing_the_node_returns_the_state_it_reads() -> None:
    node_state = NodeState(
        node_id="node-1",
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        downloads=(),
        backoff_state_by_key={},
    )

    description = DescribeNode(FakeNodeStateReader(node_state)).describe_node()

    assert description == NodeDescription(node_state=node_state)

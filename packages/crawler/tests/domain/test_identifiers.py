from catalog_matching.domain.identifiers import TargetId
from p2pwatch.domain.identifiers import NodeId


def _node_id(node_id: NodeId) -> str:
    return node_id


def _target_id(target_id: TargetId) -> str:
    return target_id


def test_a_bare_str_is_no_node_id() -> None:
    """The ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _node_id("node-a") == "node-a"  # type: ignore[arg-type]


def test_a_node_id_and_a_target_id_are_refused_for_each_other() -> None:
    """Each ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _node_id(TargetId("62a")) == "62a"  # type: ignore[arg-type]
    assert _target_id(NodeId("node-a")) == "node-a"  # type: ignore[arg-type]

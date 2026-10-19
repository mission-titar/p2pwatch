import uuid

from p2pwatch.adapters.driven.uuid4_node_id_generator import Uuid4NodeIdGenerator


def test_each_new_node_id_is_a_distinct_random_uuid() -> None:
    generator = Uuid4NodeIdGenerator()

    first, second = generator.new_node_id(), generator.new_node_id()

    assert uuid.UUID(first).version == 4
    assert first != second

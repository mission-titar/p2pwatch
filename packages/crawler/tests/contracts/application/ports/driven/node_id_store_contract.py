"""The promise of the ``NodeIdReader`` and ``NodeIdWriter`` pair."""

from abc import ABC, abstractmethod
from random import Random

import pytest

from p2pwatch.application.ports.driven.node_id_reader import NodeIdReader
from p2pwatch.application.ports.driven.node_id_writer import NodeIdWriter
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.store_error import StoreError
from tests.support.draws import draw_instant, draw_text


class NodeIdStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def writer(self) -> NodeIdWriter:
        """The writer of a store holding no node id yet."""

    @pytest.fixture
    @abstractmethod
    def reader(self) -> NodeIdReader:
        """The reader of the writer's store."""

    def test_no_node_id_is_read_before_one_is_recorded(self, reader: NodeIdReader) -> None:
        assert reader.read_node_id() is None

    def test_a_recorded_node_id_is_read_back(
        self, *, randomness: Random, writer: NodeIdWriter, reader: NodeIdReader
    ) -> None:
        node_id = NodeId(draw_text(randomness))
        writer.record_node_id(node_id, created_at=draw_instant(randomness))
        assert reader.read_node_id() == node_id

    def test_a_second_node_id_is_refused(self, *, randomness: Random, writer: NodeIdWriter) -> None:
        writer.record_node_id(NodeId(draw_text(randomness)), created_at=draw_instant(randomness))
        with pytest.raises(StoreError):
            writer.record_node_id(
                NodeId(draw_text(randomness)), created_at=draw_instant(randomness)
            )

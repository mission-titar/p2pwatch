"""The promise of the ``NodeIdReader`` and ``NodeIdWriter`` pair."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from p2pwatch.application.ports.driven.node_id_reader import NodeIdReader
from p2pwatch.application.ports.driven.node_id_writer import NodeIdWriter
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.store_error import StoreError

_CREATED_AT = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)


@dataclass(kw_only=True, frozen=True)
class NodeIdPorts:
    """The pair's two ports, which one store implements."""

    writer: NodeIdWriter
    reader: NodeIdReader


class NodeIdStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def node_id_ports(self) -> NodeIdPorts:
        """The ports of a store holding no node id yet."""

    def test_no_node_id_is_read_before_one_is_recorded(self, node_id_ports: NodeIdPorts) -> None:
        assert node_id_ports.reader.read_node_id() is None

    def test_a_recorded_node_id_is_read_back(self, node_id_ports: NodeIdPorts) -> None:
        node_id_ports.writer.record_node_id(NodeId("first-node"), created_at=_CREATED_AT)
        assert node_id_ports.reader.read_node_id() == "first-node"

    def test_a_second_node_id_is_refused(self, node_id_ports: NodeIdPorts) -> None:
        node_id_ports.writer.record_node_id(NodeId("first-node"), created_at=_CREATED_AT)
        with pytest.raises(StoreError):
            node_id_ports.writer.record_node_id(NodeId("second-node"), created_at=_CREATED_AT)

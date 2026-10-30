"""The promise of the ``NodeIdReader`` and ``NodeIdWriter`` pair."""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Protocol

import pytest

from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.store_error import StoreError

_CREATED_AT = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)


class NodeIdStore(Protocol):
    """Both ports of the pair, which one store implements."""

    def read_node_id(self) -> NodeId | None: ...

    def record_node_id(self, node_id: NodeId, *, created_at: datetime) -> None: ...


class NodeIdStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def node_id_store(self) -> NodeIdStore:
        """A store holding no node id yet."""

    def test_no_node_id_is_read_before_one_is_recorded(self, node_id_store: NodeIdStore) -> None:
        assert node_id_store.read_node_id() is None

    def test_a_recorded_node_id_is_read_back(self, node_id_store: NodeIdStore) -> None:
        node_id_store.record_node_id(NodeId("first-node"), created_at=_CREATED_AT)
        assert node_id_store.read_node_id() == "first-node"

    def test_a_second_node_id_is_refused(self, node_id_store: NodeIdStore) -> None:
        node_id_store.record_node_id(NodeId("first-node"), created_at=_CREATED_AT)
        with pytest.raises(StoreError):
            node_id_store.record_node_id(NodeId("second-node"), created_at=_CREATED_AT)

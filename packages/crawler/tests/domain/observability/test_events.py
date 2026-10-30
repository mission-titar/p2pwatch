"""Events are frozen dataclasses with business fields — construction/freeze test."""

import dataclasses

import pytest

from catalog_matching.domain.identifiers import TargetId
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import Channel, ClientName, NodeId
from p2pwatch.domain.observability.events import (
    DownloadCompleted,
    ObservationRecorded,
    TargetTitle,
)


def test_observation_recorded_carries_client_and_network() -> None:
    event = ObservationRecorded(client_name=ClientName("amuled"), channel=Channel("ed2k"))
    assert (event.client_name, event.channel) == ("amuled", "ed2k")


def test_event_is_frozen() -> None:
    event = DownloadCompleted(
        file=FileKey(network=Network.ED2K, native_id="a" * 32),
        filename="x.avi",
        target_titles=(TargetTitle(target_id=TargetId("062A"), title="t"),),
        node_id=NodeId("titar-node-1"),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.filename = "y.avi"  # type: ignore[misc]

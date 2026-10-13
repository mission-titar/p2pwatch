"""Events are frozen dataclasses with business fields — construction/freeze test."""

import dataclasses

import pytest

from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observability.events import (
    DownloadCompleted,
    ObservationRecorded,
    TargetTitle,
)


def test_observation_recorded_carries_client_and_network() -> None:
    event = ObservationRecorded(client_name="amuled", channel="ed2k")
    assert (event.client_name, event.channel) == ("amuled", "ed2k")


def test_event_is_frozen() -> None:
    event = DownloadCompleted(
        file=FileKey(Network.ED2K, "a" * 32),
        filename="x.avi",
        target_titles=(TargetTitle("062A", "t"),),
    )
    # Pass the attribute via a variable to avoid ruff B010 while still
    # triggering FrozenInstanceError at runtime (frozen=True).
    attr = "filename"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(event, attr, "y.avi")

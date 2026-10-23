import dataclasses
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.source import (
    ContactPoint,
    EarlierPoints,
    LatestPoint,
    SourceKey,
    SourceReading,
    SourceRole,
    SourceUsefulness,
    carried_role,
    carried_role_max_age,
    parse_contact_point,
)

_HASH = "31d6cfe0d16ae931b73c59d7e0c089c0"
_T0 = datetime(2026, 10, 13, 20, 0, tzinfo=UTC)


def test_source_key_is_frozen() -> None:
    key = SourceKey(Network.ED2K, _HASH)
    with pytest.raises(dataclasses.FrozenInstanceError):
        key.native_id = "autre"  # type: ignore[misc]


def test_source_id_is_the_uuid5_of_network_and_native_id_in_the_source_namespace() -> None:
    namespace = uuid.uuid5(uuid.NAMESPACE_URL, "https://mission-titar.github.io/p2pwatch/source")
    expected = uuid.uuid5(namespace, f"ed2k:{_HASH}").bytes
    assert SourceKey(Network.ED2K, _HASH).source_id == expected
    assert len(expected) == 16


def test_source_id_never_equals_the_file_id_of_the_same_native_id() -> None:
    assert SourceKey(Network.ED2K, _HASH).source_id != FileKey(Network.ED2K, _HASH).file_id


def test_source_id_differs_per_native_id() -> None:
    assert SourceKey(Network.ED2K, _HASH).source_id != SourceKey(Network.ED2K, "0" * 32).source_id


@pytest.mark.parametrize("native_id", [_HASH.upper(), _HASH[:31], _HASH + "0", "g" * 32, ""])
def test_source_key_refuses_an_ed2k_native_id_that_is_not_32_lowercase_hex(
    native_id: str,
) -> None:
    with pytest.raises(ValueError, match="32 lowercase hex"):
        SourceKey(Network.ED2K, native_id)


def test_source_roles_are_the_five_values_the_catalog_accepts() -> None:
    assert [role.value for role in SourceRole] == [
        "sending",
        "queued",
        "nothing_new",
        "standby",
        "undetermined",
    ]


def test_a_reading_in_a_passing_state_has_no_role_and_may_have_no_identity() -> None:
    reading = SourceReading(
        source=None,
        source_name="AnimuseeFMR",
        software="emule 0.50a",
        role=None,
        contact_point=None,
        connectable=None,
        raw_metadata=(("protocol_extensions", ()), ("source_origin", "kad")),
        session_received_bytes=0,
    )
    assert reading.source is None
    assert reading.role is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        reading.role = SourceRole.QUEUED  # type: ignore[misc]


def test_each_role_belongs_to_its_group() -> None:
    assert {role: role.usefulness for role in SourceRole} == {
        SourceRole.SENDING: SourceUsefulness.USEFUL,
        SourceRole.QUEUED: SourceUsefulness.USEFUL,
        SourceRole.NOTHING_NEW: SourceUsefulness.NOT_USEFUL,
        SourceRole.STANDBY: SourceUsefulness.UNKNOWN,
        SourceRole.UNDETERMINED: SourceUsefulness.UNKNOWN,
    }


@pytest.mark.parametrize(
    ("previous", "carried"),
    [
        (SourceRole.SENDING, SourceRole.QUEUED),
        (SourceRole.QUEUED, SourceRole.QUEUED),
        (SourceRole.NOTHING_NEW, SourceRole.NOTHING_NEW),
        (SourceRole.STANDBY, SourceRole.UNDETERMINED),
        (SourceRole.UNDETERMINED, SourceRole.UNDETERMINED),
        (None, SourceRole.UNDETERMINED),
    ],
)
def test_a_passing_state_carries_the_group_of_the_latest_point(
    previous: SourceRole | None, carried: SourceRole
) -> None:
    assert carried_role(previous) is carried


def test_the_tolerance_lets_one_read_be_missed() -> None:
    assert carried_role_max_age(timedelta(seconds=330)) == timedelta(seconds=990)


def test_earlier_points_of_no_point_tell_nothing() -> None:
    assert EarlierPoints.of(()) == EarlierPoints(has_useful_point=False, latest_known_at=None)


def test_earlier_points_leave_unknown_points_out_of_the_latest_known_one() -> None:
    points = (
        LatestPoint(SourceRole.NOTHING_NEW, _T0, 0),
        LatestPoint(SourceRole.STANDBY, _T0 + timedelta(hours=1), 0),
        LatestPoint(SourceRole.UNDETERMINED, _T0 + timedelta(hours=2), 0),
    )
    assert EarlierPoints.of(points) == EarlierPoints(has_useful_point=False, latest_known_at=_T0)


def test_earlier_points_tell_a_useful_point_and_the_latest_known_one() -> None:
    points = (
        LatestPoint(SourceRole.QUEUED, _T0 + timedelta(hours=1), 0),
        LatestPoint(SourceRole.NOTHING_NEW, _T0, 0),
        LatestPoint(SourceRole.STANDBY, _T0 + timedelta(hours=2), 0),
    )
    assert EarlierPoints.of(points) == EarlierPoints(
        has_useful_point=True, latest_known_at=_T0 + timedelta(hours=1)
    )


@pytest.mark.parametrize("server", ["176.103.48.36:4184", "0.0.0.0:1", "1.2.3.4:65535"])
def test_an_ed2k_contact_point_is_an_ipv4_address_and_a_port(server: str) -> None:
    assert parse_contact_point(Network.ED2K, server) == ContactPoint(Network.ED2K, server)


@pytest.mark.parametrize(
    "server",
    [
        "176.103.48.36",
        "176.103.48.36:",
        ":4184",
        "176.103.48.36:0",
        "176.103.48.36:04184",
        "176.103.48.36:65536",
        "256.103.48.36:4184",
        "176.103.48.036:4184",
        "[::1]:4184",
        "server.example:4184",
        "176.103.48.36:4184 ",
        "176.103.48.36:\u0664\u0661",
    ],
)
def test_anything_else_is_not_an_ed2k_contact_point(server: str) -> None:
    assert parse_contact_point(Network.ED2K, server) is None
    with pytest.raises(ValueError, match="a ed2k contact point is an IPv4 address and a port"):
        ContactPoint(Network.ED2K, server)

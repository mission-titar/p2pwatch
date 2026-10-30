import dataclasses
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

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
from tests.support.domain.value_bounds import (
    MALFORMED_TEXTS,
    NOT_QUANTITIES,
    QUANTITIES,
    WELL_FORMED_TEXTS,
)

_HASH = "31d6cfe0d16ae931b73c59d7e0c089c0"
_T0 = datetime(2026, 10, 13, 20, 0, tzinfo=UTC)


def test_source_key_is_frozen() -> None:
    key = SourceKey(network=Network.ED2K, native_id=_HASH)
    with pytest.raises(dataclasses.FrozenInstanceError):
        key.native_id = "autre"  # type: ignore[misc]


def test_source_id_is_the_uuid5_of_network_and_native_id_in_the_source_namespace() -> None:
    namespace = uuid.uuid5(uuid.NAMESPACE_URL, "https://mission-titar.github.io/p2pwatch/source")
    expected = uuid.uuid5(namespace, f"ed2k:{_HASH}").bytes
    assert SourceKey(network=Network.ED2K, native_id=_HASH).source_id == expected
    assert len(expected) == 16


def test_source_id_never_equals_the_file_id_of_the_same_native_id() -> None:
    assert (
        bytes(SourceKey(network=Network.ED2K, native_id=_HASH).source_id)
        != FileKey(network=Network.ED2K, native_id=_HASH).file_id
    )


def test_source_id_differs_per_native_id() -> None:
    assert (
        SourceKey(network=Network.ED2K, native_id=_HASH).source_id
        != SourceKey(network=Network.ED2K, native_id="0" * 32).source_id
    )


@pytest.mark.parametrize("native_id", [_HASH.upper(), _HASH[:31], _HASH + "0", "g" * 32, ""])
def test_source_key_refuses_an_ed2k_native_id_that_is_not_32_lowercase_hex(
    native_id: str,
) -> None:
    with pytest.raises(ValueError, match="32 lowercase hex"):
        SourceKey(network=Network.ED2K, native_id=native_id)


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


_TEXT_POSITIONS = (
    "source_name",
    "software",
    "raw_metadata key",
    "raw_metadata text",
    "raw_metadata tuple element",
)


def _reading() -> SourceReading:
    return SourceReading(
        source=SourceKey(network=Network.ED2K, native_id=_HASH),
        source_name="AnimuseeFMR",
        software="emule 0.50a",
        role=SourceRole.QUEUED,
        contact_point=None,
        connectable=True,
        raw_metadata=(
            ("protocol_extensions", ("a",)),
            ("source_origin", "kad"),
            ("shared_files_browsable", True),
        ),
        session_received_bytes=5,
    )


def _holding_text(position: str, *, text: str) -> dict[str, Any]:
    """The fields that put ``text`` at ``position`` of a reading."""
    fields_by_position: dict[str, dict[str, Any]] = {
        "source_name": {"source_name": text},
        "software": {"software": text},
        "raw_metadata key": {"raw_metadata": ((text, "kad"),)},
        "raw_metadata text": {"raw_metadata": (("source_origin", text),)},
        "raw_metadata tuple element": {"raw_metadata": (("protocol_extensions", ("a", text)),)},
    }
    return fields_by_position[position]


@pytest.mark.parametrize("text", MALFORMED_TEXTS)
@pytest.mark.parametrize("position", _TEXT_POSITIONS)
def test_a_reading_refuses_text_that_is_not_valid_utf8(*, position: str, text: str) -> None:
    with pytest.raises(ValueError, match=r"^a source reading's \w+ is not valid UTF-8$"):
        dataclasses.replace(_reading(), **_holding_text(position, text=text))


@pytest.mark.parametrize("text", WELL_FORMED_TEXTS)
@pytest.mark.parametrize("position", _TEXT_POSITIONS)
def test_a_reading_holds_valid_non_ascii_text(*, position: str, text: str) -> None:
    fields = _holding_text(position, text=text)
    reading = dataclasses.replace(_reading(), **fields)
    assert fields.items() <= dataclasses.asdict(reading).items()


@pytest.mark.parametrize("field", ["source_name", "software"])
def test_a_reading_may_have_no_name_or_software(field: str) -> None:
    fields: dict[str, Any] = {field: None}
    assert dataclasses.asdict(dataclasses.replace(_reading(), **fields))[field] is None


@pytest.mark.parametrize("quantity", NOT_QUANTITIES)
def test_a_reading_refuses_received_bytes_that_are_not_a_quantity(quantity: int) -> None:
    with pytest.raises(ValueError, match="^a source reading's session_received_bytes is not"):
        dataclasses.replace(_reading(), session_received_bytes=quantity)


@pytest.mark.parametrize("quantity", QUANTITIES)
def test_a_reading_holds_the_limits_of_a_quantity(quantity: int) -> None:
    reading = dataclasses.replace(_reading(), session_received_bytes=quantity)
    assert reading.session_received_bytes == quantity


def test_each_role_belongs_to_its_group() -> None:
    assert {role: role.usefulness for role in SourceRole} == {
        SourceRole.SENDING: SourceUsefulness.USEFUL,
        SourceRole.QUEUED: SourceUsefulness.USEFUL,
        SourceRole.NOTHING_NEW: SourceUsefulness.NOT_USEFUL,
        SourceRole.STANDBY: SourceUsefulness.UNKNOWN,
        SourceRole.UNDETERMINED: SourceUsefulness.UNKNOWN,
    }


def _passing(session_received_bytes: int) -> SourceReading:
    return SourceReading(
        source=None,
        source_name="AnimuseeFMR",
        software=None,
        role=None,
        contact_point=None,
        connectable=None,
        raw_metadata=(),
        session_received_bytes=session_received_bytes,
    )


@pytest.mark.parametrize(
    ("previous", "carried"),
    [
        (SourceRole.SENDING, SourceRole.QUEUED),
        (SourceRole.QUEUED, SourceRole.QUEUED),
        (SourceRole.NOTHING_NEW, SourceRole.NOTHING_NEW),
        (SourceRole.STANDBY, SourceRole.UNDETERMINED),
        (SourceRole.UNDETERMINED, SourceRole.UNDETERMINED),
    ],
)
def test_a_passing_state_carries_the_group_of_the_latest_point(
    *, previous: SourceRole, carried: SourceRole
) -> None:
    assert (
        carried_role(
            LatestPoint(role=previous, observed_at=_T0, session_received_bytes=5),
            reading=_passing(5),
        )
        is carried
    )


def test_a_passing_state_without_a_latest_point_is_undetermined() -> None:
    assert carried_role(None, reading=_passing(0)) is SourceRole.UNDETERMINED


@pytest.mark.parametrize(
    ("session_received_bytes", "carried"),
    [(9, SourceRole.QUEUED), (4, SourceRole.UNDETERMINED)],
    ids=["a-higher-counter", "a-lower-counter"],
)
def test_a_passing_state_carries_nothing_once_its_client_was_recreated(
    *, session_received_bytes: int, carried: SourceRole
) -> None:
    # aMule recreating the client restarts its session's received bytes.
    latest = LatestPoint(role=SourceRole.QUEUED, observed_at=_T0, session_received_bytes=5)
    assert carried_role(latest, reading=_passing(session_received_bytes)) is carried


def test_the_tolerance_lets_one_read_be_missed() -> None:
    assert carried_role_max_age(timedelta(seconds=330)) == timedelta(seconds=990)


def test_earlier_points_of_no_point_tell_nothing() -> None:
    assert EarlierPoints.of(()) == EarlierPoints(has_useful_point=False, latest_known_at=None)


def test_earlier_points_leave_unknown_points_out_of_the_latest_known_one() -> None:
    points = (
        LatestPoint(role=SourceRole.NOTHING_NEW, observed_at=_T0, session_received_bytes=0),
        LatestPoint(
            role=SourceRole.STANDBY, observed_at=_T0 + timedelta(hours=1), session_received_bytes=0
        ),
        LatestPoint(
            role=SourceRole.UNDETERMINED,
            observed_at=_T0 + timedelta(hours=2),
            session_received_bytes=0,
        ),
    )
    assert EarlierPoints.of(points) == EarlierPoints(has_useful_point=False, latest_known_at=_T0)


def test_earlier_points_tell_a_useful_point_and_the_latest_known_one() -> None:
    points = (
        LatestPoint(
            role=SourceRole.QUEUED, observed_at=_T0 + timedelta(hours=1), session_received_bytes=0
        ),
        LatestPoint(role=SourceRole.NOTHING_NEW, observed_at=_T0, session_received_bytes=0),
        LatestPoint(
            role=SourceRole.STANDBY, observed_at=_T0 + timedelta(hours=2), session_received_bytes=0
        ),
    )
    assert EarlierPoints.of(points) == EarlierPoints(
        has_useful_point=True, latest_known_at=_T0 + timedelta(hours=1)
    )


@pytest.mark.parametrize("server", ["176.103.48.36:4184", "0.0.0.0:1", "1.2.3.4:65535"])
def test_an_ed2k_contact_point_is_an_ipv4_address_and_a_port(server: str) -> None:
    assert parse_contact_point(Network.ED2K, server=server) == ContactPoint(
        network=Network.ED2K, server=server
    )


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
    assert parse_contact_point(Network.ED2K, server=server) is None
    with pytest.raises(ValueError, match="a ed2k contact point is an IPv4 address and a port"):
        ContactPoint(network=Network.ED2K, server=server)

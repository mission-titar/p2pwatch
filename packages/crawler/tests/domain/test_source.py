import dataclasses
import uuid

import pytest

from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.source import SourceKey, SourceReading, SourceRole

_HASH = "31d6cfe0d16ae931b73c59d7e0c089c0"


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
        key=None,
        name="AnimuseeFMR",
        software="emule 0.50a",
        role=None,
        contact_point=None,
        directly_reachable=None,
        raw_meta=(("protocol_extensions", ()), ("source_origin", "kad")),
        transfer_counter=0,
    )
    assert reading.key is None
    assert reading.role is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        reading.role = SourceRole.QUEUED  # type: ignore[misc]

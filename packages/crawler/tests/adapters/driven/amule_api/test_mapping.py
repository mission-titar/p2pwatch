"""Mapping of the amuleapi JSON payloads (spec amuleapi §4.2, D4/D5)."""

import dataclasses
import json
from typing import Any

import pytest

from p2pwatch.adapters.driven.amule_api.mapping import (
    map_client_status,
    map_download_status,
    map_search_results,
    map_shared_download,
    map_source,
    merge_duplicate_sources,
    offering_source_ecid,
)
from p2pwatch.domain.download.states import FailureReason, WaitingReason
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import Channel, Keyword
from p2pwatch.domain.json_object_text import JsonObjectText
from p2pwatch.domain.observation import ReportedFile
from p2pwatch.domain.source import ContactPoint, SourceKey, SourceReading, SourceRole
from p2pwatch.domain.status_reading import ChannelStatus, ClientStatus

_HASH = "8b54a3c20fae9e4b9f7e0c2c8c01b6b1"
_KEY = FileKey(network=Network.ED2K, native_id=_HASH)
# Half of a UTF-16 pair, which no UTF-8 text holds: what bytes that are not UTF-8 decode to.
_SURROGATE = "\ud800"
_REPLACEMENT = "\N{REPLACEMENT CHARACTER}"


def _result(**overrides: Any) -> dict[str, Any]:
    """A result row shaped like GET /search/{id}/results returns one."""
    row: dict[str, Any] = {
        "hash": _HASH,
        "name": "Keroro.095.avi",
        "size_bytes": 3825205248,
        "sources": {"total": 217, "complete": 142},
        "already_downloaded": False,
        "rating": 0,
        "status": "new",
        "file_type": "video",
        "directory": "",
        "media": None,
        "alternate_names": [],
        "comments": [],
    }
    row.update(overrides)
    return row


def _raw_metadata(reported_file: ReportedFile) -> dict[str, Any]:
    raw_metadata: dict[str, Any] = json.loads(reported_file.raw_metadata.text)
    return raw_metadata


def _unmapped(reported_file: ReportedFile) -> dict[str, Any]:
    unmapped: dict[str, Any] = _raw_metadata(reported_file)["unmapped"]
    return unmapped


def test_maps_a_result_to_an_observation() -> None:
    reported_files, skipped = map_search_results([_result()], keyword=Keyword("keroro"))

    assert skipped == 0
    (reported_file,) = reported_files
    assert reported_file.file == _KEY
    assert reported_file.filename == "Keroro.095.avi"
    assert reported_file.size_bytes == 3825205248
    assert reported_file.source_count == 217
    assert reported_file.keyword == "keroro"


def test_the_ed2k_only_fields_sit_beside_what_no_field_consumes() -> None:
    (reported_file,), _ = map_search_results(
        [_result(media={"codec": "H.264"})], keyword=Keyword("keroro")
    )

    raw = _raw_metadata(reported_file)
    assert raw.keys() == {"codec", "file_type", "complete_source_count", "unmapped"}
    assert (raw["codec"], raw["file_type"], raw["complete_source_count"]) == ("H.264", "video", 142)


def test_a_name_the_network_sends_never_meets_one_the_mapper_derives() -> None:
    """D4: flattened, each of these would repeat a name the mapper chose."""
    search_result = _result(
        codec="h264",
        complete_source_count=7,
        media={"codec": "xvid", "title": "Keroro"},
        **{"media.title": "top"},
    )
    (reported_file,), _ = map_search_results([search_result], keyword=Keyword("keroro"))

    raw = _raw_metadata(reported_file)
    assert (raw["codec"], raw["complete_source_count"]) == ("xvid", 142)
    unmapped = _unmapped(reported_file)
    assert unmapped["codec"] == "h264"
    assert unmapped["complete_source_count"] == "7"
    assert unmapped["media.title"] == "top"
    assert unmapped["media"] == {"title": "Keroro"}


def test_an_uppercase_hash_is_folded_to_lowercase() -> None:
    (reported_file,), _ = map_search_results(
        [_result(hash=_HASH.upper())], keyword=Keyword("keroro")
    )

    assert reported_file.file == _KEY


def test_media_fills_the_columns_that_ec_never_could() -> None:
    media = {
        "duration_seconds": 1440,
        "bitrate_kilobits_per_second": 1500,
        "codec": "H.264",
        "artist": "",
        "album": "",
        "title": "Keroro",
    }
    (reported_file,), _ = map_search_results([_result(media=media)], keyword=Keyword("keroro"))

    assert reported_file.duration_seconds == 1440
    assert reported_file.bitrate_kbps == 1500
    assert _raw_metadata(reported_file)["codec"] == "H.264"
    # artist/album/title have no column: they survive in raw_metadata (spec §4.2).
    assert _unmapped(reported_file)["media"] == {"artist": "", "album": "", "title": "Keroro"}


@pytest.mark.parametrize("media", [None, {"duration_seconds": 1440, "codec": "H.264"}])
def test_a_media_holding_no_unmapped_key_is_left_out(media: object) -> None:
    (reported_file,), _ = map_search_results([_result(media=media)], keyword=Keyword("keroro"))

    assert "media" not in _unmapped(reported_file)


def test_a_null_media_leaves_the_media_columns_empty() -> None:
    (reported_file,), _ = map_search_results([_result()], keyword=Keyword("keroro"))

    assert reported_file.duration_seconds is None
    assert reported_file.bitrate_kbps is None
    assert _raw_metadata(reported_file)["codec"] is None


def test_a_malformed_media_object_is_tolerated() -> None:
    (reported_file,), _ = map_search_results(
        [_result(media={"codec": 7})], keyword=Keyword("keroro")
    )

    assert _raw_metadata(reported_file)["codec"] is None
    assert reported_file.duration_seconds is None


def test_unmapped_keys_land_in_raw_metadata() -> None:
    (reported_file,), _ = map_search_results([_result(rating=3)], keyword=Keyword("keroro"))

    raw = _unmapped(reported_file)
    assert raw["rating"] == "3"
    assert raw["status"] == "new"
    assert raw["already_downloaded"] == "false"
    assert raw["comments"] == "[]"
    # Mapped keys are NOT duplicated into raw_metadata.
    assert "hash" not in raw
    assert "alternate_names" not in raw


def test_every_alternate_name_becomes_its_own_observation() -> None:
    """D4: amuled folds the same file's other filenames under the parent; we unfold them."""
    alternates = [
        {"ecid": 621, "name": "[Keroro].095.avi", "sources": {"total": 40, "complete": 22}},
        {"ecid": 622, "name": "sgt-frog-095.avi", "sources": {"total": 10, "complete": 3}},
    ]
    reported_files, skipped = map_search_results(
        [_result(alternate_names=alternates)], keyword=Keyword("keroro")
    )

    assert skipped == 0
    assert [reported_file.filename for reported_file in reported_files] == [
        "Keroro.095.avi",
        "[Keroro].095.avi",
        "sgt-frog-095.avi",
    ]
    # The hash and the size come from the parent, the source counts from each entry.
    assert {reported_file.file for reported_file in reported_files} == {_KEY}
    assert {reported_file.size_bytes for reported_file in reported_files} == {3825205248}
    assert [reported_file.source_count for reported_file in reported_files] == [217, 40, 10]
    assert [
        _raw_metadata(reported_file)["complete_source_count"] for reported_file in reported_files
    ] == [
        142,
        22,
        3,
    ]


def test_an_alternate_never_carries_the_volatile_ecid() -> None:
    alternate = {"ecid": 621, "name": "[Keroro].095.avi", "sources": {"total": 40}}
    reported_files, _ = map_search_results(
        [_result(alternate_names=[alternate])], keyword=Keyword("keroro")
    )

    assert "621" not in reported_files[1].raw_metadata.text


def test_a_result_without_a_usable_hash_is_skipped_and_counted() -> None:
    reported_files, skipped = map_search_results(
        [_result(hash="not-a-hash")], keyword=Keyword("keroro")
    )

    assert reported_files == ()
    assert skipped == 1


@pytest.mark.parametrize("size_bytes", [True, -1, 2**63])
def test_a_result_without_a_usable_size_is_skipped_and_counted(size_bytes: int) -> None:
    """A size read as 0 would catalogue a file aMule refuses to download."""
    reported_files, skipped = map_search_results(
        [_result(size_bytes=size_bytes)], keyword=Keyword("keroro")
    )

    assert reported_files == ()
    assert skipped == 1


def test_a_result_that_is_not_an_object_is_skipped_and_counted() -> None:
    reported_files, skipped = map_search_results(["nonsense"], keyword=Keyword("keroro"))

    assert reported_files == ()
    assert skipped == 1


def test_an_unusable_name_costs_only_its_own_observation_and_is_not_counted() -> None:
    alternates = [{"name": 7}, "nonsense", {"name": "sgt-frog-095.avi"}]
    reported_files, skipped = map_search_results(
        [_result(alternate_names=alternates)], keyword=Keyword("keroro")
    )

    assert [reported_file.filename for reported_file in reported_files] == [
        "Keroro.095.avi",
        "sgt-frog-095.avi",
    ]
    assert skipped == 0


def test_a_nameless_parent_does_not_lose_its_alternates() -> None:
    alternates = [{"name": "sgt-frog-095.avi"}]
    reported_files, skipped = map_search_results(
        [_result(name="", alternate_names=alternates)], keyword=Keyword("keroro")
    )

    assert [reported_file.filename for reported_file in reported_files] == ["sgt-frog-095.avi"]
    assert skipped == 0


def test_a_result_without_any_usable_name_is_skipped_and_counted() -> None:
    reported_files, skipped = map_search_results(
        [_result(name="", alternate_names=[{"name": 7}])], keyword=Keyword("keroro")
    )

    assert reported_files == ()
    assert skipped == 1


def test_a_malformed_alternate_names_list_is_ignored() -> None:
    reported_files, skipped = map_search_results(
        [_result(alternate_names="nope")], keyword=Keyword("keroro")
    )

    assert len(reported_files) == 1
    assert skipped == 0


def test_missing_source_counts_read_as_zero() -> None:
    (reported_file,), _ = map_search_results([_result(sources="nope")], keyword=Keyword("keroro"))

    assert reported_file.source_count == 0
    assert _raw_metadata(reported_file)["complete_source_count"] == 0


@pytest.mark.parametrize("count", ["many", -1, 2**63])
def test_a_malformed_source_count_reads_as_zero(count: object) -> None:
    (reported_file,), _ = map_search_results(
        [_result(sources={"total": count, "complete": count})], keyword=Keyword("keroro")
    )

    assert reported_file.source_count == 0
    assert _raw_metadata(reported_file)["complete_source_count"] == 0


@pytest.mark.parametrize(
    ("reported", "read"), [(0, 0), (2**63 - 1, 2**63 - 1), (-1, None), (2**63, None)]
)
def test_a_duration_or_bitrate_the_catalog_cannot_hold_reads_as_absent(
    *, reported: int, read: int | None
) -> None:
    """Neither is negative, and the catalog holds at most a signed 64-bit integer."""
    media = {"duration_seconds": reported, "bitrate_kilobits_per_second": reported}
    (reported_file,), _ = map_search_results([_result(media=media)], keyword=Keyword("keroro"))

    assert (reported_file.duration_seconds, reported_file.bitrate_kbps) == (read, read)


@pytest.mark.parametrize(
    ("name", "filename"),
    [
        (f"Keroro{_SURROGATE}.avi", f"Keroro{_REPLACEMENT}.avi"),
        # json.loads decodes with surrogatepass: U+1F600 written as CESU-8 stays two halves.
        (json.loads(b'"Keroro \xed\xa0\xbd\xed\xb8\x80.avi"'), f"Keroro {_REPLACEMENT * 2}.avi"),
    ],
)
def test_a_surrogate_in_a_filename_reads_as_a_replacement_character(
    *, name: str, filename: str
) -> None:
    """Since amuleapi writes none, one left comes from bytes that are not UTF-8."""
    (reported_file,), _ = map_search_results([_result(name=name)], keyword=Keyword("keroro"))

    assert reported_file.filename == filename


@pytest.mark.parametrize(
    ("overrides", "path", "value"),
    [
        ({f"rating{_SURROGATE}": "3"}, ("unmapped", f"rating{_REPLACEMENT}"), "3"),
        ({"rating": f"3{_SURROGATE}"}, ("unmapped", "rating"), f"3{_REPLACEMENT}"),
        ({"comments": [f"nice{_SURROGATE}"]}, ("unmapped", "comments"), f'["nice{_REPLACEMENT}"]'),
        (
            {"media": {f"title{_SURROGATE}": "Keroro"}},
            ("unmapped", "media", f"title{_REPLACEMENT}"),
            "Keroro",
        ),
        ({"media": {"codec": f"H.264{_SURROGATE}"}}, ("codec",), f"H.264{_REPLACEMENT}"),
        ({"file_type": f"video{_SURROGATE}"}, ("file_type",), f"video{_REPLACEMENT}"),
    ],
)
def test_a_surrogate_in_a_results_raw_metadata_reads_as_a_replacement_character(
    *, overrides: dict[str, Any], path: tuple[str, ...], value: str
) -> None:
    (reported_file,), _ = map_search_results([_result(**overrides)], keyword=Keyword("keroro"))

    found: Any = _raw_metadata(reported_file)
    for name in path:
        found = found[name]
    assert found == value


def test_a_non_string_file_type_is_dropped() -> None:
    (reported_file,), _ = map_search_results([_result(file_type=7)], keyword=Keyword("keroro"))

    assert _raw_metadata(reported_file)["file_type"] is None


def test_a_results_payload_that_is_not_a_list_yields_nothing() -> None:
    assert map_search_results("nope", keyword=Keyword("keroro")) == ((), 0)


def _queued(status: str, **overrides: Any) -> dict[str, Any]:
    """A row shaped like GET /downloads returns one."""
    row: dict[str, Any] = {
        "hash": _HASH,
        "size_bytes": 1000,
        "completed_bytes": 400,
        "status": status,
        "sources": {"total": 5, "unavailable": 0, "transferring": 2, "a4af": 0},
    }
    row.update(overrides)
    return row


def _download(row: object) -> DownloadStatus:
    status = map_download_status(row)
    assert status is not None
    return status


def test_maps_a_download_row_to_its_status() -> None:
    assert _download(_queued("downloading")) == DownloadStatus(
        file=_KEY,
        bytes_done=400,
        size_bytes=1000,
        completed=False,
        waiting_reason=None,
        failure_reason=None,
    )


@pytest.mark.parametrize("byte_count", [-1, 2**63])
def test_a_download_byte_count_the_catalog_cannot_hold_reads_as_zero(byte_count: int) -> None:
    status = _download(_queued("downloading", completed_bytes=byte_count, size_bytes=byte_count))

    assert (status.bytes_done, status.size_bytes) == (0, 0)


def test_only_the_completed_status_completes_a_download() -> None:
    # Every byte received is not the file verified and moved (spec stage 2, D10).
    statuses = ("completed", "completing", "downloading")
    completed = [_download(_queued(status, completed_bytes=1000)).completed for status in statuses]

    assert completed == [True, False, False]


def test_an_erroneous_download_failed_with_an_error() -> None:
    assert _download(_queued("erroneous")).failure_reason is FailureReason.ERROR


@pytest.mark.parametrize(
    ("status", "sources", "reason"),
    [
        ("insufficient_disk", {"total": 0}, WaitingReason.DISK_FULL),
        ("paused", {"total": 0}, WaitingReason.PAUSED),
        ("stopped", {"total": 0}, WaitingReason.PAUSED),
        ("waiting", {"total": 0}, WaitingReason.LOCAL_PROCESSING),
        ("hashing", {"total": 0}, WaitingReason.LOCAL_PROCESSING),
        ("allocating", {"total": 0}, WaitingReason.LOCAL_PROCESSING),
        ("completing", {"total": 0}, WaitingReason.LOCAL_PROCESSING),
        ("downloading", {"total": 0}, WaitingReason.NO_SOURCE),
        ("downloading", {}, WaitingReason.NO_SOURCE),
        ("downloading", {"total": 3, "transferring": 0}, WaitingReason.REMOTE_QUEUE),
        ("downloading", {"total": 3, "transferring": 1}, None),
        ("completed", {"total": 0}, None),
        ("erroneous", {"total": 0}, None),
    ],
)
def test_a_download_waits_for_the_first_reason_that_applies(
    *, status: str, sources: dict[str, int], reason: WaitingReason | None
) -> None:
    assert _download(_queued(status, sources=sources)).waiting_reason is reason


def test_a_status_that_is_not_a_string_waits_on_its_sources() -> None:
    # An unhashable status must not reach the status table as a key.
    row = _queued("downloading", sources={"total": 0})
    row["status"] = ["paused"]

    assert _download(row).waiting_reason is WaitingReason.NO_SOURCE


def test_a_download_status_row_without_a_usable_hash_is_dropped() -> None:
    assert map_download_status({"size_bytes": 1000, "status": "completed"}) is None
    assert map_download_status("nonsense") is None


def test_a_shared_row_reads_as_a_completed_download() -> None:
    assert map_shared_download({"hash": _HASH, "size_bytes": 10}) == DownloadStatus(
        file=_KEY,
        bytes_done=10,
        size_bytes=10,
        completed=True,
        waiting_reason=None,
        failure_reason=None,
    )
    assert map_shared_download({"name": "Keroro.095.avi"}) is None
    assert map_shared_download("nonsense") is None


def test_a_connected_high_id_and_open_kad_are_connectable() -> None:
    status = map_client_status(
        {
            "ed2k": {"state": "connected", "high_id": True, "public_ip": "210.2.150.73"},
            "kad": {"state": "connected", "firewalled_tcp": False},
        },
        version={"daemon_version": "3.0.1"},
    )

    assert status == ClientStatus(
        version="3.0.1",
        channels=(
            ChannelStatus(channel=Channel("ed2k"), connected=True, connectable=True),
            ChannelStatus(channel=Channel("kad"), connected=True, connectable=True),
        ),
    )


def test_a_low_id_and_a_firewalled_kad_are_not_connectable() -> None:
    status = map_client_status(
        {
            "ed2k": {"state": "connected", "high_id": False},
            "kad": {"state": "connected", "firewalled_tcp": True},
        },
        version={"daemon_version": "3.0.1"},
    )

    assert [channel.connectable for channel in status.channels] == [False, False]


def test_connectable_is_unknown_off_the_network() -> None:
    # Off the network, high_id false means "no id yet", not Low-ID.
    status = map_client_status(
        {
            "ed2k": {"state": "connecting", "high_id": False},
            "kad": {"state": "connecting", "firewalled_tcp": None},
        },
        version={"daemon_version": "3.0.1"},
    )

    assert [channel.connected for channel in status.channels] == [False, False]
    assert [channel.connectable for channel in status.channels] == [None, None]


def test_a_missing_reachability_flag_on_the_network_is_unknown() -> None:
    status = map_client_status(
        {"ed2k": {"state": "connected"}, "kad": {"state": "connected"}}, version={}
    )

    assert [channel.connectable for channel in status.channels] == [None, None]


def test_an_empty_version_and_status_degrade_to_unknown() -> None:
    # daemon_version is "" while EC is down.
    status = map_client_status("nonsense", version={"daemon_version": ""})

    assert status.version is None
    assert [channel.channel for channel in status.channels] == ["ed2k", "kad"]
    assert [channel.connected for channel in status.channels] == [False, False]


def test_a_surrogate_in_amules_version_reads_as_a_replacement_character() -> None:
    status = map_client_status({}, version={"daemon_version": f"3.1.0{_SURROGATE}"})

    assert status.version == f"3.1.0{_REPLACEMENT}"


def _client_row(**overrides: Any) -> dict[str, Any]:
    """A row of GET /downloads/{hash}/clients: the /clients list object plus its file relation."""
    row: dict[str, Any] = {
        "ecid": 4382,
        "name": "AnimuseeFMR",
        "user_hash": "1F2E3A4B5C6D7E8F90A1B2C3D4E5F607",
        "ip": "203.0.113.42",
        "country_code": "de",
        "port": 4662,
        "software": "emule",
        "software_version": "0.50a",
        "reported_os": "Linux",
        "upload_state": "idle",
        "download_state": "queued",
        "ident_state": "identified",
        "download_file_name": "Keroro.095.avi",
        "upload_file_name": None,
        "upload_file_hash": None,
        "download_file_hash": _HASH,
        "uploaded_bytes_session": 0,
        "downloaded_bytes_session": 1024,
        "uploaded_bytes_total": 452000000,
        "downloaded_bytes_total": 189000000,
        "upload_speed_bytes_per_second": 0,
        "download_speed_bytes_per_second": 1000,
        "upload_queue_position": 0,
        "remote_queue_position": 12,
        "upload_queue_score": 150,
        "obfuscation_state": "enabled",
        "connected": True,
        "protocol_extensions": ["extended_source_exchange"],
        "friend_slot": False,
        "friend": False,
        "credit_ratio": 2.34,
        "source_origin": "kad",
        "parts_offered_count": 42,
        "client_mod_name": None,
        "shared_files_browsable": False,
        "part_progress_percent": 87.5,
        "role": "downloading_from",
        "a4af": False,
    }
    row.update(overrides)
    return row


def _client_detail(**overrides: Any) -> dict[str, Any]:
    """GET /clients/{ecid}: the /clients list object plus its detail-only fields."""
    detail = {key: field for key, field in _client_row().items() if key not in ("role", "a4af")}
    detail.update(
        ed2k_user_id=3232238090,
        high_id=True,
        server_ip="176.103.48.36",
        server_port=4184,
        server_name="eMule Security",
        kad_port=4672,
    )
    detail.update(overrides)
    return detail


def test_a_source_maps_to_a_reading_of_its_row_and_its_detail() -> None:
    assert map_source(_client_row(), detail=_client_detail()) == SourceReading(
        source=SourceKey(network=Network.ED2K, native_id="1f2e3a4b5c6d7e8f90a1b2c3d4e5f607"),
        source_name="AnimuseeFMR",
        software="emule 0.50a",
        role=SourceRole.QUEUED,
        contact_point=ContactPoint(network=Network.ED2K, server="176.103.48.36:4184"),
        connectable=True,
        raw_metadata=JsonObjectText(
            text='{"client_mod_name": null, "ident_state": "identified",'
            ' "protocol_extensions": ["extended_source_exchange"], "reported_os": "Linux",'
            ' "server_name": "eMule Security", "shared_files_browsable": false,'
            ' "source_origin": "kad"}'
        ),
        session_received_bytes=1024,
    )


def test_no_address_of_the_peer_reaches_the_reading() -> None:
    """D7: the addresses are set on the row and the detail, and none is copied."""
    addresses = {
        "ip": "198.51.100.77",
        "port": 46629,
        "kad_port": 46739,
        "country_code": "xq",
        "ed2k_user_id": 1298396614,
    }
    row = _client_row(**addresses)
    del row["ed2k_user_id"]  # detail-only

    reading = map_source(row, detail=_client_detail(**addresses))

    serialized = json.dumps(dataclasses.asdict(reading))
    assert [address for address in addresses.values() if str(address) in serialized] == []


@pytest.mark.parametrize(
    ("relation", "a4af", "kept"),
    [
        ("downloading_from", False, True),
        ("both", False, True),
        ("downloading_from", True, True),
        ("none", True, True),
        ("uploading_to", True, True),
        ("uploading_to", False, False),
        ("none", False, False),
        (None, None, False),
    ],
)
def test_a_row_is_a_source_when_we_ask_it_the_file_or_it_is_parked_on_another(
    *, relation: str | None, a4af: bool | None, kept: bool
) -> None:
    """D1: a row that only takes the file from us offers nothing, so its detail is not asked."""
    assert offering_source_ecid(_client_row(role=relation, a4af=a4af)) == (4382 if kept else None)


@pytest.mark.parametrize(
    "row", ["nonsense", _client_row(ecid=None), _client_row(ecid=True), _client_row(ecid=-1)]
)
def test_a_row_without_an_ecid_to_ask_is_no_source(row: object) -> None:
    assert offering_source_ecid(row) is None


@pytest.mark.parametrize(
    ("relation", "a4af", "role"),
    [
        ("downloading_from", False, SourceRole.QUEUED),
        ("both", False, SourceRole.QUEUED),
        ("none", True, SourceRole.STANDBY),
        ("uploading_to", True, SourceRole.STANDBY),
    ],
)
def test_a_source_we_ask_takes_its_state_and_a_parked_one_is_standby(
    *, relation: str, a4af: bool, role: SourceRole
) -> None:
    reading = map_source(_client_row(role=relation, a4af=a4af), detail=_client_detail())

    assert reading.role == role


@pytest.mark.parametrize(
    ("state", "role"),
    [
        ("downloading", SourceRole.SENDING),
        ("queued", SourceRole.QUEUED),
        ("no_needed_parts", SourceRole.NOTHING_NEW),
        *(
            (passing, None)
            for passing in (
                "idle",
                "connecting",
                "connected",
                "waiting_callback",
                "waiting_callback_kad",
                "requesting_hashset",
                "too_many_connections",
                "too_many_connections_kad",
                "remote_queue_full",
            )
        ),
        *(
            (state, SourceRole.UNDETERMINED)
            for state in ("low_to_low_ip", "banned", "error", "unknown", "a_future_state", None)
        ),
    ],
)
def test_a_sources_role_is_what_its_download_state_says_of_the_parts_we_lack(
    *, state: str | None, role: SourceRole | None
) -> None:
    """D3: a passing state reads ``None``, for the writer to carry the latest point's group."""
    reading = map_source(_client_row(download_state=state), detail=_client_detail())

    assert reading.role == role


def test_a_parked_source_is_standby_whatever_it_does_for_another_file() -> None:
    # download_state is the client's, so on an A4AF row it describes the other file.
    row = _client_row(role="none", a4af=True, download_state="downloading")

    assert map_source(row, detail=_client_detail()).role is SourceRole.STANDBY


@pytest.mark.parametrize("user_hash", [None, "", "0" * 32, "8b54a3c2", "zz" * 16])
def test_a_source_without_a_usable_user_hash_has_no_identity(user_hash: str | None) -> None:
    """D7: amuleapi reports a peer that has not sent its hash yet with 32 zeros."""
    reading = map_source(_client_row(user_hash=user_hash), detail=_client_detail())

    assert reading.source is None
    assert reading.source_name == "AnimuseeFMR"


def test_a_source_without_a_user_hash_key_has_no_identity() -> None:
    row = _client_row()
    del row["user_hash"]

    assert map_source(row, detail=_client_detail()).source is None


@pytest.mark.parametrize(
    ("software", "version", "expected"),
    [("emule", "0.50a", "emule 0.50a"), ("unknown", None, "unknown"), (None, None, None)],
)
def test_a_sources_software_joins_its_client_and_version(
    *, software: str | None, version: str | None, expected: str | None
) -> None:
    reading = map_source(_client_row(software=software, software_version=version), detail={})

    assert reading.software == expected


def test_a_sparse_row_and_detail_keep_the_meta_keys_they_carry_and_read_unknown() -> None:
    reading = map_source(
        {"role": "downloading_from", "name": "", "ident_state": "unknown"}, detail={}
    )

    assert (reading.source_name, reading.software) == (None, None)
    assert (reading.contact_point, reading.connectable) == (None, None)
    assert reading.raw_metadata == JsonObjectText(text='{"ident_state": "unknown"}')
    assert reading.session_received_bytes == 0


@pytest.mark.parametrize("received", [-1, 2**63])
def test_a_session_counter_the_catalog_cannot_hold_reads_as_zero(received: int) -> None:
    reading = map_source(_client_row(downloaded_bytes_session=received), detail=_client_detail())

    assert reading.session_received_bytes == 0


def test_a_surrogate_in_a_sources_name_or_software_reads_as_a_replacement_character() -> None:
    row = _client_row(name=f"Animusee{_SURROGATE}", software_version=f"0.50a{_SURROGATE}")
    reading = map_source(row, detail=_client_detail())

    assert (reading.source_name, reading.software) == (
        f"Animusee{_REPLACEMENT}",
        f"emule 0.50a{_REPLACEMENT}",
    )


@pytest.mark.parametrize(
    ("protocol_extensions", "kept"),
    [
        ([], []),
        (["ipv6", 7], ["ipv6", "7"]),
        ({"bits": 3}, '{"bits": 3}'),
        (1.5, "1.5"),
        (None, None),
        (f"ipv6{_SURROGATE}", f"ipv6{_REPLACEMENT}"),
        ([f"ipv6{_SURROGATE}"], [f"ipv6{_REPLACEMENT}"]),
        ({f"bits{_SURROGATE}": 3}, f'{{"bits{_REPLACEMENT}": 3}}'),
    ],
)
def test_a_meta_value_is_kept_in_a_shape_the_catalog_stores(
    *, protocol_extensions: object, kept: object
) -> None:
    reading = map_source(
        _client_row(protocol_extensions=protocol_extensions), detail=_client_detail()
    )

    assert json.loads(reading.raw_metadata.text)["protocol_extensions"] == kept


@pytest.mark.parametrize(
    ("server_ip", "server_port", "contact_point"),
    [
        ("176.103.48.36", 4184, ContactPoint(network=Network.ED2K, server="176.103.48.36:4184")),
        (None, None, None),
        ("176.103.48.36", None, None),
        (None, 4184, None),
        ("176.103.48.36", 0, None),
        ("176.103.48.36", True, None),
        ("2001:db8::1", 4184, None),
    ],
)
def test_a_sources_contact_point_is_its_server_as_ip_and_port(
    *, server_ip: str | None, server_port: object, contact_point: ContactPoint | None
) -> None:
    """D3: anything but an eD2k ``ip:port`` reads unknown."""
    detail = _client_detail(server_ip=server_ip, server_port=server_port)

    assert map_source(_client_row(), detail=detail).contact_point == contact_point


def test_the_server_name_is_kept_unknown_when_the_server_is() -> None:
    detail = _client_detail(server_ip=None, server_port=None, server_name=None)

    reading = map_source(_client_row(), detail=detail)

    assert json.loads(reading.raw_metadata.text)["server_name"] is None


@pytest.mark.parametrize(
    ("ed2k_user_id", "high_id", "connectable"),
    [
        (3232238090, True, True),
        (4242, False, False),
        (0, False, None),
        (None, False, None),
        (-1, True, None),
        (3232238090, None, None),
        (3232238090, "true", None),
    ],
)
def test_a_source_is_directly_reachable_when_its_ed2k_id_is_a_high_id(
    *, ed2k_user_id: int | None, high_id: object, connectable: bool | None
) -> None:
    """D3: without an eD2k id yet (0), ``high_id`` false says nothing."""
    detail = _client_detail(ed2k_user_id=ed2k_user_id, high_id=high_id)

    assert map_source(_client_row(), detail=detail).connectable is connectable


def _reading(
    role: SourceRole | None, *, counter: int = 0, native_id: str | None = "1f" * 16, name: str = "x"
) -> SourceReading:
    key = SourceKey(network=Network.ED2K, native_id=native_id) if native_id is not None else None
    return SourceReading(
        source=key,
        source_name=name,
        software=None,
        role=role,
        contact_point=None,
        connectable=None,
        raw_metadata=JsonObjectText(text="{}"),
        session_received_bytes=counter,
    )


# D7's order, the most informative first: a passing state (None) above `undetermined`.
_INFORMATIVE: list[SourceRole | None] = [
    SourceRole.SENDING,
    SourceRole.QUEUED,
    SourceRole.NOTHING_NEW,
    None,
    SourceRole.UNDETERMINED,
    SourceRole.STANDBY,
]


@pytest.mark.parametrize(
    ("better", "worse"), [pair for pair in zip(_INFORMATIVE, _INFORMATIVE[1:], strict=False)]
)
def test_two_rows_of_one_source_keep_the_more_informative_role_and_the_larger_counter(
    *, better: SourceRole | None, worse: SourceRole | None
) -> None:
    """D7: a user hash is not unique among a client's simultaneous connections."""
    for rows in (
        [_reading(better, counter=5), _reading(worse, counter=9)],
        [_reading(worse, counter=9), _reading(better, counter=5)],
    ):
        assert merge_duplicate_sources(rows) == (_reading(better, counter=9),)


def test_two_rows_without_a_hash_are_one_source_by_name_only() -> None:
    rows = [
        _reading(SourceRole.QUEUED, native_id=None, name="peer"),
        _reading(SourceRole.STANDBY, native_id=None, name="peer"),
        _reading(SourceRole.STANDBY, native_id=None, name="other"),
        _reading(SourceRole.STANDBY, name="peer"),
        _reading(SourceRole.STANDBY, native_id="2e" * 16, name="peer"),
    ]

    assert merge_duplicate_sources(rows) == (rows[0], *rows[2:])


def test_rows_with_neither_hash_nor_name_are_never_merged() -> None:
    nameless = SourceReading(
        source=None,
        source_name=None,
        software=None,
        role=SourceRole.QUEUED,
        contact_point=None,
        connectable=None,
        raw_metadata=JsonObjectText(text="{}"),
        session_received_bytes=0,
    )

    assert merge_duplicate_sources([nameless, nameless]) == (nameless, nameless)

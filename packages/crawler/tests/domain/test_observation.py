import dataclasses

import pytest

from catalog_matching.domain.models import FileCandidate
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observation import ReportedFile, candidate_from_fields, fold_raw_metadata

_KEY = FileKey(Network.ED2K, "31d6cfe0d16ae931b73c59d7e0c089c0")


def _full_reported_file() -> ReportedFile:
    return ReportedFile(
        file=_KEY,
        filename="Keroro 062A.avi",
        size_bytes=3 * 1024 * 1024,
        source_count=5,
        keyword="keroro",
        duration_seconds=1234,
        bitrate_kbps=1500,
        raw_metadata=(("0x0308", "0"), ("codec", None), ("complete_source_count", 2)),
    )


def test_file_observation_is_frozen_and_holds_fields() -> None:
    reported_file = _full_reported_file()
    assert reported_file.file == _KEY
    assert reported_file.filename == "Keroro 062A.avi"
    assert reported_file.size_bytes == 3 * 1024 * 1024
    assert reported_file.source_count == 5
    assert reported_file.keyword == "keroro"
    assert reported_file.raw_metadata == (
        ("0x0308", "0"),
        ("codec", None),
        ("complete_source_count", 2),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        reported_file.filename = "autre"  # type: ignore[misc]


def test_media_fields_and_raw_metadata_default_to_absent() -> None:
    reported_file = ReportedFile(
        file=_KEY,
        filename="Keroro 062A.avi",
        size_bytes=100,
        source_count=0,
        keyword="keroro",
    )
    assert reported_file.duration_seconds is None
    assert reported_file.bitrate_kbps is None
    assert reported_file.raw_metadata == ()


def test_to_candidate_converts_units_with_media_metadata() -> None:
    # exactly 3 MiB -> size_mib == 3.0 (DECISION 8: 1 MiB = 1024*1024 bytes).
    candidate = _full_reported_file().to_candidate()
    assert candidate == FileCandidate(
        filename="Keroro 062A.avi",
        size_mib=3.0,
        duration_seconds=1234.0,
        bitrate_kbps=1500.0,
    )


def test_to_candidate_maps_absent_media_metadata_to_none() -> None:
    reported_file = ReportedFile(
        file=_KEY,
        filename="Keroro 062A.avi",
        size_bytes=524288,  # 0.5 MiB
        source_count=1,
        keyword="keroro",
    )
    candidate = reported_file.to_candidate()
    assert candidate == FileCandidate(
        filename="Keroro 062A.avi",
        size_mib=0.5,
        duration_seconds=None,
        bitrate_kbps=None,
    )


def test_candidate_from_fields_converts_units_with_media_metadata() -> None:
    # exactly 3 MiB -> size_mib == 3.0 (DECISION 8: 1 MiB = 1024*1024 bytes).
    candidate = candidate_from_fields(
        filename="Keroro 062A.avi",
        size_bytes=3 * 1024 * 1024,
        duration_seconds=1234,
        bitrate_kbps=1500,
    )
    assert candidate == FileCandidate(
        filename="Keroro 062A.avi",
        size_mib=3.0,
        duration_seconds=1234.0,
        bitrate_kbps=1500.0,
    )


def test_candidate_from_fields_maps_absent_media_metadata_to_none() -> None:
    candidate = candidate_from_fields(
        filename="Keroro 062A.avi",
        size_bytes=524288,  # 0.5 MiB
        duration_seconds=None,
        bitrate_kbps=None,
    )
    assert candidate == FileCandidate(
        filename="Keroro 062A.avi",
        size_mib=0.5,
        duration_seconds=None,
        bitrate_kbps=None,
    )


def test_fold_raw_metadata_appends_the_three_values_after_the_pairs() -> None:
    folded = fold_raw_metadata((("0x0308", "0"),), "xvid", "Video", 2)
    assert folded == (
        ("0x0308", "0"),
        ("codec", "xvid"),
        ("file_type", "Video"),
        ("complete_source_count", 2),
    )


def test_fold_raw_metadata_keeps_an_absent_value_as_none() -> None:
    folded = fold_raw_metadata((), None, None, 0)
    assert folded == (("codec", None), ("file_type", None), ("complete_source_count", 0))

import dataclasses
from typing import Any

import pytest

from catalog_matching.domain.models import FileCandidate
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import Keyword
from p2pwatch.domain.observation import ReportedFile, candidate_from_fields, fold_raw_metadata
from tests.support.domain.value_bounds import (
    MALFORMED_TEXTS,
    NOT_QUANTITIES,
    QUANTITIES,
    WELL_FORMED_TEXTS,
)

_KEY = FileKey(network=Network.ED2K, native_id="31d6cfe0d16ae931b73c59d7e0c089c0")


def _full_reported_file() -> ReportedFile:
    return ReportedFile(
        file=_KEY,
        filename="Keroro 062A.avi",
        size_bytes=3 * 1024 * 1024,
        source_count=5,
        keyword=Keyword("keroro"),
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
        keyword=Keyword("keroro"),
    )
    assert reported_file.duration_seconds is None
    assert reported_file.bitrate_kbps is None
    assert reported_file.raw_metadata == ()


_TEXT_POSITIONS = ("filename", "keyword", "raw_metadata key", "raw_metadata text")

_QUANTITY_FIELDS = ("size_bytes", "source_count", "duration_seconds", "bitrate_kbps")


def _holding_text(position: str, *, text: str) -> dict[str, Any]:
    """The fields that put ``text`` at ``position`` of a reported file."""
    fields_by_position: dict[str, dict[str, Any]] = {
        "filename": {"filename": text},
        "keyword": {"keyword": Keyword(text)},
        "raw_metadata key": {"raw_metadata": ((text, "0"),)},
        "raw_metadata text": {"raw_metadata": (("0x0308", text),)},
    }
    return fields_by_position[position]


@pytest.mark.parametrize("text", MALFORMED_TEXTS)
@pytest.mark.parametrize("position", _TEXT_POSITIONS)
def test_a_reported_file_refuses_text_that_is_not_valid_utf8(*, position: str, text: str) -> None:
    with pytest.raises(ValueError, match=r"^a reported file's \w+ is not valid UTF-8$"):
        dataclasses.replace(_full_reported_file(), **_holding_text(position, text=text))


@pytest.mark.parametrize("text", WELL_FORMED_TEXTS)
@pytest.mark.parametrize("position", _TEXT_POSITIONS)
def test_a_reported_file_holds_valid_non_ascii_text(*, position: str, text: str) -> None:
    fields = _holding_text(position, text=text)
    reported_file = dataclasses.replace(_full_reported_file(), **fields)
    assert fields.items() <= dataclasses.asdict(reported_file).items()


@pytest.mark.parametrize("quantity", NOT_QUANTITIES)
@pytest.mark.parametrize("field", _QUANTITY_FIELDS)
def test_a_reported_file_refuses_an_integer_that_is_not_a_quantity(
    *, field: str, quantity: int
) -> None:
    fields: dict[str, Any] = {field: quantity}
    with pytest.raises(ValueError, match=f"^a reported file's {field} is not a quantity"):
        dataclasses.replace(_full_reported_file(), **fields)


@pytest.mark.parametrize("quantity", QUANTITIES)
@pytest.mark.parametrize("field", _QUANTITY_FIELDS)
def test_a_reported_file_holds_the_limits_of_a_quantity(*, field: str, quantity: int) -> None:
    fields: dict[str, Any] = {field: quantity}
    reported_file = dataclasses.replace(_full_reported_file(), **fields)
    assert dataclasses.asdict(reported_file)[field] == quantity


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
        keyword=Keyword("keroro"),
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
    folded = fold_raw_metadata(
        (("0x0308", "0"),), codec="xvid", file_type="Video", complete_source_count=2
    )
    assert folded == (
        ("0x0308", "0"),
        ("codec", "xvid"),
        ("file_type", "Video"),
        ("complete_source_count", 2),
    )


def test_fold_raw_metadata_keeps_an_absent_value_as_none() -> None:
    folded = fold_raw_metadata((), codec=None, file_type=None, complete_source_count=0)
    assert folded == (("codec", None), ("file_type", None), ("complete_source_count", 0))

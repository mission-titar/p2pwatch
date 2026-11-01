"""The draws of a file's observations, for the contracts that seed through ``ObservationWriter``."""

from datetime import datetime
from random import Random

from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import Keyword, NodeId
from p2pwatch.domain.json_object_text import JsonObjectText
from p2pwatch.domain.observation import FileObservation, ReportedFile
from tests.support.draws import draw_instant, draw_quantities, draw_quantity, draw_text

# Each quantity of a reported file takes a residue of its own.
_SIZE, _SOURCES, _DURATION, _BITRATE = range(4)
# Each text in a length band of its own, a native id 32 long, only a JSON text holding a "{".
_KEYWORD_LENGTHS = range(1, 16)
_NODE_ID_LENGTHS = range(16, 32)
_FILENAME_LENGTHS = range(33, 81)


def draw_file(randomness: Random) -> FileKey:
    """An eD2k file of a drawn native id."""
    return FileKey(network=Network.ED2K, native_id=f"{randomness.getrandbits(128):032x}")


def draw_source_counts(randomness: Random, *, count: int) -> tuple[int, ...]:
    """``count`` distinct source counts, ascending."""
    return draw_quantities(randomness, residue=_SOURCES, count=count)


def draw_reported_file(
    randomness: Random,
    *,
    file: FileKey,
    has_media: bool,
    filename: str | None = None,
    source_count: int | None = None,
) -> ReportedFile:
    """A report of ``file``, ``filename`` and ``source_count`` drawn unless given, both media
    fields drawn or both ``None``."""
    return ReportedFile(
        file=file,
        filename=draw_text(randomness, lengths=_FILENAME_LENGTHS) if filename is None else filename,
        size_bytes=draw_quantity(randomness, residue=_SIZE),
        source_count=(
            draw_quantity(randomness, residue=_SOURCES) if source_count is None else source_count
        ),
        keyword=Keyword(draw_text(randomness, lengths=_KEYWORD_LENGTHS)),
        duration_seconds=draw_quantity(randomness, residue=_DURATION) if has_media else None,
        bitrate_kbps=draw_quantity(randomness, residue=_BITRATE) if has_media else None,
        raw_metadata=_draw_raw_metadata(randomness),
    )


def _draw_raw_metadata(randomness: Random) -> JsonObjectText:
    key = draw_text(randomness, lengths=_KEYWORD_LENGTHS)
    return JsonObjectText.from_object({key: draw_text(randomness, lengths=_FILENAME_LENGTHS)})


def draw_file_observation(
    randomness: Random,
    *,
    file: FileKey,
    has_media: bool,
    observed_at: datetime | None = None,
    filename: str | None = None,
    source_count: int | None = None,
) -> FileObservation:
    """An observation of a report ``draw_reported_file`` draws, by a drawn node, ``observed_at``
    drawn unless given."""
    return FileObservation(
        reported_file=draw_reported_file(
            randomness,
            file=file,
            has_media=has_media,
            filename=filename,
            source_count=source_count,
        ),
        observed_at=draw_instant(randomness) if observed_at is None else observed_at,
        node_id=NodeId(draw_text(randomness, lengths=_NODE_ID_LENGTHS)),
    )

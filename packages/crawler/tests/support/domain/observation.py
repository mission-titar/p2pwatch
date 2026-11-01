"""The draws of a file's observations, for the contracts that seed through ``ObservationWriter``."""

from datetime import datetime
from random import Random

from p2pwatch.application.ports.driven.observation_writer import ObservationWriter
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import Keyword, NodeId
from p2pwatch.domain.json_object_text import JsonObjectText
from p2pwatch.domain.observation import FileObservation, ReportedFile
from tests.support.draws import draw_instant, draw_quantity, draw_text


def draw_file(randomness: Random) -> FileKey:
    """An eD2k file of a drawn native id."""
    return FileKey(network=Network.ED2K, native_id=f"{randomness.getrandbits(128):032x}")


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
        filename=draw_text(randomness) if filename is None else filename,
        size_bytes=draw_quantity(randomness),
        source_count=draw_quantity(randomness) if source_count is None else source_count,
        keyword=Keyword(draw_text(randomness)),
        duration_seconds=draw_quantity(randomness) if has_media else None,
        bitrate_kbps=draw_quantity(randomness) if has_media else None,
        raw_metadata=JsonObjectText.from_object({draw_text(randomness): draw_text(randomness)}),
    )


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
        node_id=NodeId(draw_text(randomness)),
    )


def draw_observed_file(
    randomness: Random, *, observation_writer: ObservationWriter, filename: str | None = None
) -> FileKey:
    """A drawn file, once ``observation_writer`` has recorded a drawn observation of it, of
    ``filename`` if given."""
    file = draw_file(randomness)
    observation_writer.record_observation(
        draw_file_observation(randomness, file=file, has_media=True, filename=filename)
    )
    return file

"""The draws of our downloads' source points, for the contracts that seed through
``SourcePointWriter``."""

from dataclasses import replace
from datetime import datetime
from random import Random

from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.json_object_text import JsonObjectText
from p2pwatch.domain.source import ContactPoint, SourceKey, SourcePoint, SourceReading, SourceRole
from tests.support.draws import draw_quantity, draw_text


def draw_source_key(randomness: Random) -> SourceKey:
    """An eD2k source of a drawn user hash."""
    return SourceKey(network=Network.ED2K, native_id=f"{randomness.getrandbits(128):032x}")


def draw_source_reading(
    randomness: Random,
    *,
    source: SourceKey | None,
    role: SourceRole | None,
    source_name: str | None = None,
) -> SourceReading:
    """A connectable reading of ``source`` with ``role``: its texts, ``source_name`` unless given,
    its contact point and its session's received bytes drawn."""
    return SourceReading(
        source=source,
        source_name=draw_text(randomness) if source_name is None else source_name,
        software=draw_text(randomness),
        role=role,
        contact_point=_draw_contact_point(randomness),
        connectable=True,
        raw_metadata=JsonObjectText.from_object({draw_text(randomness): draw_text(randomness)}),
        session_received_bytes=draw_quantity(randomness),
    )


def _draw_contact_point(randomness: Random) -> ContactPoint:
    octets = ".".join(str(randomness.randrange(256)) for _ in range(4))
    return ContactPoint(network=Network.ED2K, server=f"{octets}:{randomness.randrange(1, 65536)}")


def draw_source_point(
    randomness: Random,
    *,
    file: FileKey,
    source: SourceKey | None,
    role: SourceRole,
    observed_at: datetime,
    node_id: NodeId | None = None,
    source_name: str | None = None,
) -> SourcePoint:
    """A point of ``source`` on ``file`` with ``role``, which its reading holds, by ``node_id``
    drawn unless given, of a reading ``draw_source_reading`` draws."""
    return SourcePoint(
        file=file,
        reading=draw_source_reading(randomness, source=source, role=role, source_name=source_name),
        role=role,
        observed_at=observed_at,
        node_id=NodeId(draw_text(randomness)) if node_id is None else node_id,
    )


def draw_point_read_again(
    randomness: Random,
    *,
    point: SourcePoint,
    observed_at: datetime,
    session_received_bytes: int | None = None,
) -> SourcePoint:
    """``point``'s variant read again at ``observed_at``, its session's received bytes drawn
    unless given."""
    reading = replace(
        point.reading,
        session_received_bytes=draw_quantity(randomness)
        if session_received_bytes is None
        else session_received_bytes,
    )
    return replace(point, reading=reading, observed_at=observed_at)

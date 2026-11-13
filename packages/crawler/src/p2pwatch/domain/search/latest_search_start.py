"""A client's latest search start in one scope of a channel, the start of a persisted wait."""

from dataclasses import dataclass
from datetime import datetime

from p2pwatch.domain.identifiers import Channel


@dataclass(kw_only=True, frozen=True)
class LatestSearchStart:
    """The latest start ``started_at`` on the wall clock in ``scope``, a part of ``channel`` its
    client's adapter spaces apart: ``''`` for the whole channel, a Kad word on Kad."""

    channel: Channel
    scope: str
    started_at: datetime

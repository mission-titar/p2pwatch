"""When a client last started a search, kept so that a client built anew keeps the spacing."""

from dataclasses import dataclass
from datetime import datetime

from p2pwatch.domain.identifiers import Channel


@dataclass(kw_only=True, frozen=True)
class LatestSearchStart:
    """A client's latest search start on ``channel``, at ``started_at`` on the wall clock, in the
    ``scope`` its adapter spaces: ``''`` for all of eD2k, the Kad word ``keroro`` on Kad."""

    channel: Channel
    scope: str
    started_at: datetime

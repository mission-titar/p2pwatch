"""The draws of the search backoff's states, for the contracts that seed through
``BackoffStateWriter``."""

from datetime import timedelta
from random import Random

from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from tests.support.draws import draw_instant, draw_quantity, draw_text

# Below 10**9 seconds: from 2**33, a delay stored as REAL seconds loses its microseconds.
_DELAY_END_MICROS = 10**9 * 10**6


def draw_backoff_key(
    randomness: Random, *, has_channel: bool, client_name: ClientName | None = None
) -> BackoffKey:
    """A drawn channel of ``client_name``, else the whole client, ``client_name`` drawn unless
    given."""
    return BackoffKey(
        client_name=ClientName(draw_text(randomness)) if client_name is None else client_name,
        channel=Channel(draw_text(randomness)) if has_channel else None,
    )


def draw_backoff_state(randomness: Random) -> BackoffState:
    """A wait of at least one attempt, from a drawn instant, its delay drawn to the microsecond."""
    return BackoffState(
        attempts=draw_quantity(randomness) + 1,
        started_at=draw_instant(randomness),
        delay=timedelta(microseconds=randomness.randrange(_DELAY_END_MICROS)),
    )

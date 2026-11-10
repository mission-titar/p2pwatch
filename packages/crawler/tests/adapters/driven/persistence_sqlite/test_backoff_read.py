"""``backoff_read``'s own tests: a row as its key and state, a value no store writes."""

from datetime import timedelta
from typing import Any

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.backoff_read import backoff_from_row
from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError
from p2pwatch.adapters.driven.persistence_sqlite.micros import micros_to_instant
from p2pwatch.adapters.driven.persistence_sqlite.named_row import NamedRow
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState

_ROW: dict[str, Any] = {
    "client_name": "amule",
    "channel": "kad",
    "attempts": 3,
    "started_at_micros": 1_780_000_000_000_000,
    "delay_seconds": 2.5,
}


@pytest.mark.parametrize("channel", ["kad", None], ids=["a channel", "the whole client"])
def test_a_row_is_read_as_its_key_and_its_state(channel: str | None) -> None:
    assert backoff_from_row(NamedRow(_ROW | {"channel": channel})) == (
        BackoffKey(
            client_name=ClientName("amule"), channel=None if channel is None else Channel(channel)
        ),
        BackoffState(
            attempts=3,
            started_at=micros_to_instant(1_780_000_000_000_000),
            delay=timedelta(seconds=2.5),
        ),
    )


@pytest.mark.parametrize(
    "corruption",
    [{"delay_seconds": float("inf")}, {"started_at_micros": 2**62}],
    ids=["infinite delay", "start past year 9999"],
)
def test_a_stored_value_no_store_writes_raises_persistence_error(
    corruption: dict[str, Any],
) -> None:
    with pytest.raises(PersistenceError, match="^a stored value cannot be read: "):
        backoff_from_row(NamedRow(_ROW | corruption))

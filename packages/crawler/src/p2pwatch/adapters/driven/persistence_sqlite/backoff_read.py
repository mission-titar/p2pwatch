"""Every read of a backoff state, ``local.db``'s ``backoff_states`` row as its key and state."""

from datetime import timedelta

from p2pwatch.adapters.driven.persistence_sqlite.errors import wrap_stored_value_errors
from p2pwatch.adapters.driven.persistence_sqlite.micros import micros_to_instant
from p2pwatch.adapters.driven.persistence_sqlite.named_row import NamedRow
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState


@wrap_stored_value_errors()
def backoff_from_row(row: NamedRow) -> tuple[BackoffKey, BackoffState]:
    """A row of ``backoff_states`` as its key and its state."""
    backoff_key = BackoffKey(
        client_name=ClientName(row["client_name"]),
        channel=None if row["channel"] is None else Channel(row["channel"]),
    )
    return backoff_key, BackoffState(
        attempts=row["attempts"],
        started_at=micros_to_instant(row["started_at_micros"]),
        delay=timedelta(seconds=row["delay_seconds"]),
    )

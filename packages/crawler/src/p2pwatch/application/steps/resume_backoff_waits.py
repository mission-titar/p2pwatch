"""``resume_backoff_waits``: the search backoff a previous run saved, loaded at the start."""

from p2pwatch.application.ports.driven.backoff_state_reader import BackoffStateReader
from p2pwatch.application.steps.search_worker import BackoffRegistry


def resume_backoff_waits(
    backoff: BackoffRegistry, backoff_state_reader: BackoffStateReader
) -> None:
    """Loads into ``backoff`` the waits saved last, each holding what is left of it."""
    backoff.load_from(backoff_state_reader.read_backoff_states())

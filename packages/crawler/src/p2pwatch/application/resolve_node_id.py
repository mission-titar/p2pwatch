"""The node's id: the one ``crawler.yml`` configures, else the one ``local.db`` holds."""

from p2pwatch.ports.clock import WallClock
from p2pwatch.ports.local_state_repository import LocalStateRepository


def resolve_node_id(
    configured_node_id: str | None, local_state: LocalStateRepository, wall_clock: WallClock
) -> str:
    """The configured ``node_id`` when there is one, else the stored one, created on first use."""
    if configured_node_id is not None:
        return configured_node_id
    return local_state.get_or_create_node_id(wall_clock.now())

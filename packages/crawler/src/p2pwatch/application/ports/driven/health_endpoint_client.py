"""``HealthEndpointClient``: the node's ``/health``, as its webui answers it."""

from abc import ABC, abstractmethod


class HealthEndpointClient(ABC):
    """Reads the node's health from its webui's ``/health``."""

    @abstractmethod
    def is_node_healthy(self) -> bool:
        """True when ``/health`` answers 200 within the client's timeout, else False; never
        raises."""

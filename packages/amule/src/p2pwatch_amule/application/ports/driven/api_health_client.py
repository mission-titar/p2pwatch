from abc import ABC, abstractmethod


class ApiHealthClient(ABC):
    """Reads whether amuleapi answers, linked to amuled."""

    @abstractmethod
    def is_api_ready(self) -> bool:
        """True when amuleapi answers and reports its link to amuled, else False; never raises."""

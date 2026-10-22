from abc import ABC, abstractmethod
from pathlib import PurePath


class StepOutputWriter(ABC):
    """Hands the workflow's next step what the bump wrote."""

    @abstractmethod
    def write_step_outputs(self, version: str, body_path: PurePath) -> None:
        """Announces the new pin's version and the path of the pull request body."""

from abc import ABC, abstractmethod
from pathlib import PurePath


class DockerfileReader(ABC):
    """Reads the Dockerfile that pins aMule."""

    @abstractmethod
    def read_dockerfile(self, dockerfile_path: PurePath) -> str:
        """The Dockerfile's text; raises ``OSError`` when it cannot be read."""

from abc import ABC, abstractmethod
from typing import Any


class RepoReader(ABC):
    """Reads one GitHub repository: its REST API and its files at a ref."""

    @abstractmethod
    def json(self, path: str) -> Any: ...

    @abstractmethod
    def file(self, ref: str, path: str) -> str: ...

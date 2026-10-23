from abc import ABC, abstractmethod
from pathlib import PurePath


class TemplateReader(ABC):
    """Reads a directory's Jinja templates."""

    @abstractmethod
    def read_templates(self, templates_directory: PurePath) -> dict[PurePath, str]:
        """The text of every `*.html` under *templates_directory*, by its path under it, in path
        order."""

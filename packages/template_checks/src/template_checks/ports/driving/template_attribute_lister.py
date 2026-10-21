"""``TemplateAttributeLister``: lists the attribute names templates read."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import PurePath


@dataclass(frozen=True)
class TemplateAttributeListing:
    """The attribute names a directory's templates read."""

    template_attributes: frozenset[str]


class TemplateAttributeLister(ABC):
    """Lists the attribute names a directory's templates read, which vulture cannot see."""

    @abstractmethod
    def list_template_attributes(self, templates_directory: PurePath) -> TemplateAttributeListing:
        """Every `x.name` a template under *templates_directory* reads."""

"""``LogicFreeChecker``: checks templates hold no logic."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import PurePath


@dataclass(frozen=True)
class LogicFreeReport:
    """Each logic construct a directory's templates hold, or why one does not parse."""

    problems: tuple[str, ...]


class LogicFreeChecker(ABC):
    """Checks a directory's templates only read the values their displays computed."""

    @abstractmethod
    def check_logic_free(self, templates_directory: PurePath) -> LogicFreeReport:
        """The logic constructs of the templates under *templates_directory*, in path order."""

from pathlib import PurePath

from template_checks.application.ports.driving.logic_free_checker import (
    LogicFreeChecker,
    LogicFreeReport,
)
from template_checks.domain.broken_input_error import BrokenInputError
from template_checks.domain.logic_constructs import LogicConstruct


class FakeLogicFreeChecker(LogicFreeChecker):
    """Reports the problems it is given, or raises its broken input, recording each directory
    it is asked for."""

    def __init__(
        self, *problems: LogicConstruct, broken_input: BrokenInputError | None = None
    ) -> None:
        self._problems = problems
        self._broken_input = broken_input
        self.templates_directories: list[PurePath] = []

    def check_logic_free(self, templates_directory: PurePath) -> LogicFreeReport:
        self.templates_directories.append(templates_directory)
        if self._broken_input is not None:
            raise self._broken_input
        return LogicFreeReport(problems=self._problems)

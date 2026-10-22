from pathlib import PurePath

from template_checks.application.ports.driving.logic_free_checker import (
    LogicFreeChecker,
    LogicFreeReport,
)


class FakeLogicFreeChecker(LogicFreeChecker):
    """Reports the problems it is given, recording each directory it is asked for."""

    def __init__(self, *problems: str) -> None:
        self._problems = problems
        self.templates_directories: list[PurePath] = []

    def check_logic_free(self, templates_directory: PurePath) -> LogicFreeReport:
        self.templates_directories.append(templates_directory)
        return LogicFreeReport(problems=self._problems)

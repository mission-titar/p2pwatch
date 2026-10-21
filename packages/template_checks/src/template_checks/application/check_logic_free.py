"""Checks a directory's templates are logic-free."""

from pathlib import PurePath

from template_checks.domain.logic_constructs import find_logic_constructs
from template_checks.ports.driven.template_reader import TemplateReader
from template_checks.ports.driving.logic_free_checker import LogicFreeChecker, LogicFreeReport


class CheckLogicFree(LogicFreeChecker):
    """Over the templates its reader reads."""

    def __init__(self, *, template_reader: TemplateReader) -> None:
        self._template_reader = template_reader

    def check_logic_free(self, templates_directory: PurePath) -> LogicFreeReport:
        templates_by_path = self._template_reader.read_templates(templates_directory)
        return LogicFreeReport(problems=find_logic_constructs(templates_by_path))

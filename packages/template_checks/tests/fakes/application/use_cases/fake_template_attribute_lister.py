from pathlib import PurePath

from template_checks.application.ports.driving.template_attribute_lister import (
    TemplateAttributeLister,
    TemplateAttributeListing,
)
from template_checks.domain.broken_input_error import BrokenInputError


class FakeTemplateAttributeLister(TemplateAttributeLister):
    """Lists the attributes it is given, or raises its broken input, recording each directory
    it is asked for."""

    def __init__(
        self, *template_attributes: str, broken_input: BrokenInputError | None = None
    ) -> None:
        self._template_attributes = frozenset(template_attributes)
        self._broken_input = broken_input
        self.templates_directories: list[PurePath] = []

    def list_template_attributes(self, templates_directory: PurePath) -> TemplateAttributeListing:
        self.templates_directories.append(templates_directory)
        if self._broken_input is not None:
            raise self._broken_input
        return TemplateAttributeListing(template_attributes=self._template_attributes)

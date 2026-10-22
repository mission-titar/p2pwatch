from pathlib import PurePath

from template_checks.application.ports.driving.template_attribute_lister import (
    TemplateAttributeLister,
    TemplateAttributeListing,
)


class FakeTemplateAttributeLister(TemplateAttributeLister):
    """Lists the attributes it is given, recording each directory it is asked for."""

    def __init__(self, *template_attributes: str) -> None:
        self._template_attributes = frozenset(template_attributes)
        self.templates_directories: list[PurePath] = []

    def list_template_attributes(self, templates_directory: PurePath) -> TemplateAttributeListing:
        self.templates_directories.append(templates_directory)
        return TemplateAttributeListing(template_attributes=self._template_attributes)

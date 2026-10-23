"""Lists the attribute names a directory's templates read."""

from pathlib import PurePath

from template_checks.application.ports.driven.template_reader import TemplateReader
from template_checks.application.ports.driving.template_attribute_lister import (
    TemplateAttributeLister,
    TemplateAttributeListing,
)
from template_checks.domain.template_attributes import find_template_attributes


class ListTemplateAttributes(TemplateAttributeLister):
    """Over the templates its reader reads."""

    def __init__(self, *, template_reader: TemplateReader) -> None:
        self._template_reader = template_reader

    def list_template_attributes(self, templates_directory: PurePath) -> TemplateAttributeListing:
        templates_by_path = self._template_reader.read_templates(templates_directory)
        return TemplateAttributeListing(
            template_attributes=find_template_attributes(templates_by_path)
        )

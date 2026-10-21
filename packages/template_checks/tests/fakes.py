from collections.abc import Mapping
from pathlib import PurePath

from template_checks.ports.driven.template_reader import TemplateReader


class FakeTemplateReader(TemplateReader):
    """Holds the templates of one directory, by their path relative to it."""

    def __init__(
        self, templates_directory: PurePath, templates_by_path: Mapping[PurePath, str]
    ) -> None:
        self._templates_directory = templates_directory
        self._templates_by_path = templates_by_path

    def read_templates(self, templates_directory: PurePath) -> dict[PurePath, str]:
        assert templates_directory == self._templates_directory
        return dict(self._templates_by_path)

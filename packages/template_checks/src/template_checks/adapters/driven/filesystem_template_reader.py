from pathlib import Path, PurePath

from template_checks.application.ports.driven.template_reader import TemplateReader


class FilesystemTemplateReader(TemplateReader):
    """The `*.html` files under the directory each call is given, at any depth."""

    def read_templates(self, templates_directory: PurePath) -> dict[PurePath, str]:
        directory = Path(templates_directory)
        return {
            template_path.relative_to(directory): template_path.read_text(encoding="utf-8")
            for template_path in sorted(directory.rglob("*.html"))
        }

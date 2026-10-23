from pathlib import Path, PurePath

from template_checks.application.ports.driven.template_reader import TemplateReader
from template_checks.domain.broken_input_error import BrokenInputError


class FilesystemTemplateReader(TemplateReader):
    """The `*.html` files under the directory each call is given, at any depth, by their path under
    it as given."""

    def read_templates(self, templates_directory: PurePath) -> dict[PurePath, str]:
        directory = Path(templates_directory)
        # `walk` rather than `rglob`, which skips an absent or unreadable directory silently.
        template_paths = sorted(
            parent / filename
            for parent, _, filenames in directory.walk(on_error=_raise_broken_input)
            for filename in filenames
            if filename.endswith(".html")
        )
        return {template_path: _read_template(template_path) for template_path in template_paths}


def _raise_broken_input(error: OSError) -> None:
    """Raises the directory *error* could not list as a broken input."""
    raise BrokenInputError(f"{error.filename}: {error.strerror}") from error


def _read_template(template_path: Path) -> str:
    """The text of *template_path*, or a broken input naming it."""
    try:
        return template_path.read_text(encoding="utf-8")
    except OSError as error:
        raise BrokenInputError(f"{template_path}: {error.strerror}") from error
    except UnicodeDecodeError as error:
        raise BrokenInputError(f"{template_path}: not UTF-8") from error

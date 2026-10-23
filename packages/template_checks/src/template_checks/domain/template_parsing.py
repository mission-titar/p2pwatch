"""A template's syntax tree, read by Jinja's parser."""

from pathlib import PurePath

from jinja2 import Environment, TemplateSyntaxError, nodes

from template_checks.domain.broken_input_error import BrokenInputError


def parse_template(template_path: PurePath, template_text: str) -> nodes.Template:
    """The syntax tree of *template_text*, read at *template_path*."""
    try:
        return Environment().parse(template_text)
    except TemplateSyntaxError as error:
        raise BrokenInputError(
            f"{template_path.as_posix()}:{error.lineno}: {error.message}"
        ) from error

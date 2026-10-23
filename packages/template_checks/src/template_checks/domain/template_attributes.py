"""The attribute names templates read, unseen by vulture: its `--ignore-names`."""

from collections.abc import Mapping
from pathlib import PurePath

from jinja2 import nodes

from template_checks.domain.template_parsing import parse_template


def find_template_attributes(templates_by_path: Mapping[PurePath, str]) -> frozenset[str]:
    """Every `x.name` one of *templates_by_path* reads."""
    template_attributes: set[str] = set()
    for template_path, template_text in templates_by_path.items():
        template = parse_template(template_path, template_text)
        template_attributes.update(node.attr for node in template.find_all(nodes.Getattr))
    return frozenset(template_attributes)

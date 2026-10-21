"""The attribute names templates read, unseen by vulture: its `--ignore-names`."""

from collections.abc import Iterable

from jinja2 import Environment, nodes


def find_template_attributes(template_texts: Iterable[str]) -> frozenset[str]:
    """Every `x.name` one of *template_texts* reads."""
    environment = Environment()
    template_attributes: set[str] = set()
    for template_text in template_texts:
        template = environment.parse(template_text)
        template_attributes.update(node.attr for node in template.find_all(nodes.Getattr))
    return frozenset(template_attributes)

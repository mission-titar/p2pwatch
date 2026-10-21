"""The attribute names the webui's templates read, unseen by vulture: its `--ignore-names`."""

from pathlib import Path

from jinja2 import Environment, nodes

from template_checks.ports.driven.template_reader import TemplateReader


def find_read_names(templates_dir: Path, *, template_reader: TemplateReader) -> frozenset[str]:
    """Every `x.name` a template under *templates_dir* reads."""
    environment = Environment()
    read_names: set[str] = set()
    for text in template_reader.read_templates(templates_dir).values():
        template = environment.parse(text)
        read_names.update(node.attr for node in template.find_all(nodes.Getattr))
    return frozenset(read_names)


def main(templates_dir: Path, *, template_reader: TemplateReader) -> None:
    """Prints the names the templates under *templates_dir* read, sorted and comma-joined."""
    print(",".join(sorted(find_read_names(templates_dir, template_reader=template_reader))))

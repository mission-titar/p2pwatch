"""The attribute names the webui's templates read, unseen by vulture: its `--ignore-names`."""

from pathlib import Path

from jinja2 import Environment, nodes


def find_read_names(directory: Path) -> frozenset[str]:
    """Every `x.name` a template under *directory* reads."""
    environment = Environment()
    read_names: set[str] = set()
    for template_path in sorted(directory.rglob("*.html")):
        template = environment.parse(template_path.read_text(encoding="utf-8"))
        read_names.update(node.attr for node in template.find_all(nodes.Getattr))
    return frozenset(read_names)


def main(templates_dir: Path) -> None:
    """Prints the names the templates under *templates_dir* read, sorted and comma-joined."""
    print(",".join(sorted(find_read_names(templates_dir))))

"""The logic a template holds, read from Jinja's syntax tree: what a logic-free one refuses."""

from collections.abc import Iterator, Mapping
from pathlib import PurePath

from jinja2 import Environment, TemplateSyntaxError, nodes

# Text, names, attributes at any depth, and the structure; `For` and `Const` are allowed apart.
_ALLOWED_NODE_TYPES: frozenset[type[nodes.Node]] = frozenset(
    {
        nodes.Template,
        nodes.Output,
        nodes.TemplateData,
        nodes.Name,
        nodes.Getattr,
        nodes.Extends,
        nodes.Block,
        nodes.Include,
    }
)


def find_logic_constructs(templates_by_path: Mapping[PurePath, str]) -> tuple[str, ...]:
    """The problem naming each logic construct of *templates_by_path*, or why one does not
    parse, in path order."""
    environment = Environment()
    problems: list[str] = []
    for template_path, template_text in templates_by_path.items():
        try:
            template = environment.parse(template_text)
        except TemplateSyntaxError as error:
            problems.append(f"{template_path.as_posix()}:{error.lineno}: {error.message}")
            continue
        problems.extend(
            f"{template_path.as_posix()}:{node.lineno}: {construct} is not logic-free"
            for node, construct in _find_refused_nodes(template)
        )
    return tuple(problems)


def _find_refused_nodes(node: nodes.Node) -> Iterator[tuple[nodes.Node, str]]:
    """Each node under *node* a logic-free template refuses, with its construct's name."""
    if isinstance(node, nodes.For):
        if node.test is not None:
            yield node, "For with an if filter"
    elif type(node) not in _ALLOWED_NODE_TYPES:
        yield node, type(node).__name__
    for child in node.iter_child_nodes():
        if not _is_template_name(node, child):
            yield from _find_refused_nodes(child)


def _is_template_name(node: nodes.Node, child: nodes.Node) -> bool:
    """Whether *child* is the constant name of the template *node* extends or includes."""
    return (
        isinstance(node, nodes.Extends | nodes.Include)
        and child is node.template
        and isinstance(child, nodes.Const)
    )

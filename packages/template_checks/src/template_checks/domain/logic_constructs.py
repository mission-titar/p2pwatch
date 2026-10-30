"""The logic a template holds, read from Jinja's syntax tree: what a logic-free one refuses."""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import PurePath

from jinja2 import nodes

from template_checks.domain.template_parsing import parse_template

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


@dataclass(kw_only=True, frozen=True)
class RefusedNode:
    """A node of a type a logic-free template refuses, by the name of its type."""

    template_path: PurePath
    line_number: int
    node_type: str


@dataclass(kw_only=True, frozen=True)
class FilteredLoop:
    """A `for` with an `if` filter, refused though a bare `for` is allowed."""

    template_path: PurePath
    line_number: int


type LogicConstruct = RefusedNode | FilteredLoop


def find_logic_constructs(
    templates_by_path: Mapping[PurePath, str],
) -> tuple[LogicConstruct, ...]:
    """Each logic construct of *templates_by_path*, in path order."""
    return tuple(
        logic_construct
        for template_path, template_text in templates_by_path.items()
        for logic_construct in _find_logic_constructs_under(
            template_path, node=parse_template(template_path, template_text=template_text)
        )
    )


def _find_logic_constructs_under(
    template_path: PurePath, *, node: nodes.Node
) -> Iterator[LogicConstruct]:
    """Each logic construct under *node*, *node* included."""
    if isinstance(node, nodes.For):
        if node.test is not None:
            yield FilteredLoop(template_path=template_path, line_number=node.lineno)
    elif type(node) not in _ALLOWED_NODE_TYPES:
        yield RefusedNode(
            template_path=template_path, line_number=node.lineno, node_type=type(node).__name__
        )
    for child in node.iter_child_nodes():
        if not _is_template_name(node, child=child):
            yield from _find_logic_constructs_under(template_path, node=child)


def _is_template_name(node: nodes.Node, *, child: nodes.Node) -> bool:
    """Whether *child* is the constant name of the template *node* extends or includes."""
    return (
        isinstance(node, nodes.Extends | nodes.Include)
        and child is node.template
        and isinstance(child, nodes.Const)
    )

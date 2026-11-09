"""The matcher config's fragments and its graph checked, once the config adapter built it."""

import re
import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePath

from p2pwatch.domain.config_problem import ConfigProblem, key_path
from p2pwatch.domain.matching.config import (
    AllDefinition,
    AnyDefinition,
    CoverageDefinition,
    MatcherConfig,
    NotDefinition,
    Operand,
    RegexDefinition,
    TokenDefinition,
    TokenReference,
)
from p2pwatch.domain.matching.identifiers import TargetId
from p2pwatch.domain.matching.interpolation import PLACEHOLDER, TARGET_PLACEHOLDERS, interpolate
from p2pwatch.domain.matching.models import TargetSegment


def has_control_character(text: str) -> bool:
    """Whether ``text`` holds a control character (``Cc``: C0, DEL, C1), which no identifier
    holds: the files page splits target ids and rule names on U+001F."""
    return any(unicodedata.category(char) == "Cc" for char in text)


def fragment_problems(
    fragments: Mapping[str, str], *, file_path: PurePath
) -> tuple[ConfigProblem, ...]:
    """Each fragment named like a target placeholder, and each one citing a fragment: a fragment
    is raw regex text, one level deep."""
    return tuple(
        ConfigProblem(file_path=file_path, key=key_path("fragments", name), message=message)
        for name, text in fragments.items()
        for message in _fragment_messages(name, text=text, fragments=fragments)
    )


def _fragment_messages(name: str, *, text: str, fragments: Mapping[str, str]) -> list[str]:
    collides = ["collides with a target placeholder"] if name in TARGET_PLACEHOLDERS else []
    return collides + [
        f"references fragment {cited!r}"
        for cited in PLACEHOLDER.findall(text)
        if cited in fragments
    ]


def expand_fragments(pattern: str, *, fragments: Mapping[str, str]) -> str:
    """Substitutes ``{fragment}``; target placeholders are left for per-target interpolation."""
    return PLACEHOLDER.sub(lambda m: fragments.get(m.group(1), m.group(0)), pattern)


_DEFAULT_MAX_DEPTH = 32

# Holds every target placeholder, so that any regex's interpolation is checked at load.
_PROBE_TARGET = TargetSegment(
    season=2,
    seasonal_number=11,
    absolute_number=62,
    letter="a",
    title="probe",
)

type _Citation = tuple[str, str | TokenReference]
type _Edge = tuple[str, str]


def cross_value_problems(
    config: MatcherConfig,
    *,
    fragments: Mapping[str, str],
    file_path: PurePath,
    max_depth: int = _DEFAULT_MAX_DEPTH,
) -> tuple[ConfigProblem, ...]:
    """The problems of ``config`` and the ``fragments`` its regexes hold, which no single value
    shows: fragments, references, vetoes, overrides, cycles, the depth when no cycle, then the
    regexes, which a fragment problem leaves unchecked since they hold the fragments."""
    problems_of_fragments = fragment_problems(fragments, file_path=file_path)
    token_citations = {
        name: tuple(_citations(definition, key=key_path("tokens", name)))
        for name, definition in config.tokens.items()
    }
    citations = (
        *(citation for cited in token_citations.values() for citation in cited),
        *(
            citation
            for index, rule in enumerate(config.rules)
            for citation in _citations(rule.expression, key=f"rules[{index}]")
        ),
    )
    edges = {
        name: [(_name_key(citation), _cited_name(citation)) for citation in cited]
        for name, cited in token_citations.items()
    }
    problems = (
        *_reference_problems(citations, tokens=config.tokens),
        *_veto_problems(config.vetoes, tokens=config.tokens),
        *_graph_problems(edges, max_depth=max_depth),
        *(() if problems_of_fragments else _regex_problems(config.tokens)),
    )
    return problems_of_fragments + tuple(
        ConfigProblem(file_path=file_path, key=key, message=message) for key, message in problems
    )


def _citations(operand: Operand | TokenDefinition, *, key: str) -> Iterator[_Citation]:
    """Each token name ``operand`` cites, at its key in the file."""
    match operand:
        case str() | TokenReference():
            yield key, operand
        case NotDefinition():
            yield from _citations(operand.operand, key=f"{key}.not")
        case AllDefinition() | AnyDefinition():
            expression_key = "all" if isinstance(operand, AllDefinition) else "any"
            for index, child in enumerate(operand.operands):
                yield from _citations(child, key=f"{key}.{expression_key}[{index}]")
        case _:
            return


def _cited_name(citation: _Citation) -> str:
    _, cited = citation
    return cited if isinstance(cited, str) else cited.name


def _name_key(citation: _Citation) -> str:
    key, cited = citation
    return key if isinstance(cited, str) else f"{key}.token"


def _reference_problems(
    citations: Sequence[_Citation], *, tokens: Mapping[str, TokenDefinition]
) -> Iterator[tuple[str, str]]:
    for citation in citations:
        key, cited = citation
        definition = tokens.get(_cited_name(citation))
        if definition is None:
            yield _name_key(citation), _unknown_token(_cited_name(citation))
        elif isinstance(cited, TokenReference) and not isinstance(definition, CoverageDefinition):
            overrides = {"min_coverage": cited.min_coverage, "min_similarity": cited.min_similarity}
            for field_name, value in overrides.items():
                if value is not None:
                    yield f"{key}.{field_name}", "can only override a coverage token"


def _veto_problems(
    vetoes: Sequence[str], *, tokens: Mapping[str, TokenDefinition]
) -> Iterator[tuple[str, str]]:
    first_indexes: dict[str, int] = {}
    for index, name in enumerate(vetoes):
        if name not in tokens:
            yield f"vetoes[{index}]", _unknown_token(name)
        if (first_index := first_indexes.setdefault(name, index)) != index:
            yield f"vetoes[{index}]", f"same token as vetoes[{first_index}]"


def _graph_problems(
    edges: Mapping[str, Sequence[_Edge]], *, max_depth: int
) -> Iterator[tuple[str, str]]:
    """Each citation closing a cycle, else the deepest token past ``max_depth``: the walk keeps
    its own stack, so a long chain never reaches the interpreter's recursion limit."""
    depths: dict[str, int] = {}
    cycles: list[tuple[str, str]] = []
    for root in edges:
        if root in depths:
            continue
        path = {root: None}
        pending = [iter(edges[root])]
        while pending:
            edge = next(pending[-1], None)
            if edge is None:
                name, _ = path.popitem()
                pending.pop()
                cited_depths = (depths.get(cited, 0) for _, cited in edges[name])
                depths[name] = 1 + max(cited_depths, default=0)
                continue
            key, cited = edge
            if cited in path:
                names = list(path)
                cycle = " -> ".join([*names[names.index(cited) :], cited])
                cycles.append((key, f"closes the reference cycle {cycle}"))
            elif cited in edges and cited not in depths:
                path[cited] = None
                pending.append(iter(edges[cited]))
    yield from cycles
    deepest = max(depths, key=depths.__getitem__, default=None)
    if not cycles and deepest is not None and depths[deepest] > max_depth:
        message = f"resolves through {depths[deepest]} levels of tokens, past the bound {max_depth}"
        yield key_path("tokens", deepest), message


def _unknown_token(name: str) -> str:
    return f"references the unknown token {name!r}"


def _regex_problems(tokens: Mapping[str, TokenDefinition]) -> Iterator[tuple[str, str]]:
    """Each placeholder a regex cites that no target fills, else each regex that does not
    compile under ``re`` as the engine's."""
    for name, definition in tokens.items():
        if not isinstance(definition, RegexDefinition):
            continue
        cited = dict.fromkeys(PLACEHOLDER.findall(definition.pattern))
        if unknown := [
            placeholder for placeholder in cited if placeholder not in TARGET_PLACEHOLDERS
        ]:
            for placeholder in unknown:
                yield (
                    key_path("tokens", name, "regex"),
                    f"cites the placeholder '{{{placeholder}}}', neither a fragment nor a target "
                    "field",
                )
            continue
        try:
            re.compile(interpolate(definition.pattern, target=_PROBE_TARGET), re.ASCII)
        except re.error as error:
            yield key_path("tokens", name, "regex"), f"does not compile as a regex: {error}"


@dataclass(kw_only=True, frozen=True)
class TargetDuplicate:
    """A target at ``index`` whose ``target_id`` the target at ``first_index`` holds first."""

    index: int
    first_index: int


def duplicate_targets(targets: Sequence[TargetSegment]) -> tuple[TargetDuplicate, ...]:
    """Each target of ``targets`` whose id an earlier one holds (``target_id`` upper-cases the
    letter): the engine's tie-break needs unique ids."""
    first_indexes: dict[TargetId, int] = {}
    return tuple(
        TargetDuplicate(index=index, first_index=first_index)
        for index, target in enumerate(targets)
        if (first_index := first_indexes.setdefault(target.target_id, index)) != index
    )

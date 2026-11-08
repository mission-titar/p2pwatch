"""The matcher config's fragments and its graph checked, once the config adapter built it."""

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePath

from p2pwatch.domain.config_problem import ConfigProblem
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
from p2pwatch.domain.matching.interpolation import (
    PLACEHOLDER,
    TARGET_PLACEHOLDERS,
    InterpolationError,
    interpolate,
)
from p2pwatch.domain.matching.models import TargetSegment


class MatchingConfigError(Exception):
    """A matcher config whose graph fails at load (reference, veto, override, cycle, regex)."""


class UnknownTokenError(MatchingConfigError):
    """A reference points to a token missing from the table."""


class CycleError(MatchingConfigError):
    """The token->token reference graph contains a cycle (the message names it)."""


class DepthExceededError(MatchingConfigError):
    """The resolution depth exceeds the bound (default 32)."""


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
        ConfigProblem(file_path=file_path, key=f"fragments.{name}", message=message)
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

# Probe target for the compile-check: provides season/seasonal_number/absolute_number/
# letter/title so that the interpolation of any RegexDefinition is testable at load time.
_PROBE_TARGET = TargetSegment(
    season=2,
    seasonal_number=11,
    absolute_number=62,
    letter="a",
    title="probe",
)


def _operand_token_names(operand: Operand) -> tuple[str, ...]:
    """Names of tokens directly referenced by an operand (str, TokenReference or inline)."""
    if isinstance(operand, str):
        return (operand,)
    if isinstance(operand, TokenReference):
        return (operand.name,)
    if isinstance(operand, NotDefinition):
        return _operand_token_names(operand.operand)
    # AllDefinition | AnyDefinition
    token_names: list[str] = []
    for child in operand.operands:
        token_names.extend(_operand_token_names(child))
    return tuple(token_names)


def _definition_token_names(token_definition: TokenDefinition) -> tuple[str, ...]:
    """Names of tokens directly referenced by a definition (empty for a leaf)."""
    if isinstance(token_definition, AllDefinition | AnyDefinition):
        token_names: list[str] = []
        for child in token_definition.operands:
            token_names.extend(_operand_token_names(child))
        return tuple(token_names)
    if isinstance(token_definition, NotDefinition):
        return _operand_token_names(token_definition.operand)
    return ()


def _operand_token_references(operand: Operand) -> tuple[TokenReference, ...]:
    """All TokenReferences (with their overrides) reachable from an operand."""
    if isinstance(operand, TokenReference):
        return (operand,)
    if isinstance(operand, NotDefinition):
        return _operand_token_references(operand.operand)
    if isinstance(operand, AllDefinition | AnyDefinition):
        token_references: list[TokenReference] = []
        for child in operand.operands:
            token_references.extend(_operand_token_references(child))
        return tuple(token_references)
    return ()  # str (bare name) -> no TokenReference


def _definition_token_references(token_definition: TokenDefinition) -> tuple[TokenReference, ...]:
    """All TokenReferences of a composite definition (empty for a leaf)."""
    if isinstance(token_definition, AllDefinition | AnyDefinition):
        token_references: list[TokenReference] = []
        for child in token_definition.operands:
            token_references.extend(_operand_token_references(child))
        return tuple(token_references)
    if isinstance(token_definition, NotDefinition):
        return _operand_token_references(token_definition.operand)
    return ()


def _check_overrides_only_on_coverage(config: MatcherConfig) -> None:
    """A min_coverage/min_similarity override is only legal on a coverage token (EBNF §8.3).

    Checked HERE (not at parsing) so as not to depend on the definition order: a forward
    reference to a coverage token must be accepted.
    """
    token_references: list[TokenReference] = []
    for token_definition in config.tokens.values():
        token_references.extend(_definition_token_references(token_definition))
    for rule in config.rules:
        token_references.extend(_operand_token_references(rule.condition))
    for token_reference in token_references:
        if (
            token_reference.min_coverage is not None or token_reference.min_similarity is not None
        ) and not isinstance(config.tokens.get(token_reference.name), CoverageDefinition):
            raise MatchingConfigError(
                "min_coverage/min_similarity override forbidden on non-coverage token "
                f"{token_reference.name!r}"
            )


def _check_references_exist(config: MatcherConfig) -> None:
    """Every reference (in a composite token OR a rule) must exist."""
    known = set(config.tokens)
    for token_definition in config.tokens.values():
        for token_name in _definition_token_names(token_definition):
            if token_name not in known:
                raise UnknownTokenError(f"reference to an unknown token: {token_name!r}")
    for rule in config.rules:
        for token_name in _operand_token_names(rule.condition):
            if token_name not in known:
                raise UnknownTokenError(
                    f"rule {rule.name!r}: reference to an unknown token: {token_name!r}"
                )


def _check_vetoes(config: MatcherConfig) -> None:
    """Every veto names a known token, at most once."""
    seen: set[str] = set()
    for name in config.vetoes:
        if name not in config.tokens:
            raise UnknownTokenError(f"veto references an unknown token: {name!r}")
        if name in seen:
            raise MatchingConfigError(f"duplicate veto: {name!r}")
        seen.add(name)


def _check_acyclic(config: MatcherConfig, *, max_depth: int) -> None:
    """Detects a cycle in the token->token graph and NAMES it (cf. spec §8.4).

    The ``len(stack) >= max_depth`` guard also bounds the recursion: a path deeper than
    ``max_depth`` is already a depth violation, raised cleanly here (avoids a Python
    ``RecursionError`` on a pathological chain).
    """
    graph = {
        name: _definition_token_names(token_definition)
        for name, token_definition in config.tokens.items()
    }
    visiting: set[str] = set()
    done: set[str] = set()
    stack: list[str] = []

    def walk(name: str) -> None:
        if name in done:
            return
        if name in visiting:
            cycle = stack[stack.index(name) :] + [name]
            raise CycleError(f"reference cycle: {' -> '.join(cycle)}")
        if len(stack) >= max_depth:
            tail = " -> ".join([*stack[-3:], name])
            raise DepthExceededError(f"resolution depth > {max_depth} (chain: … -> {tail})")
        visiting.add(name)
        stack.append(name)
        for token_name in graph.get(
            name, ()
        ):  # token_name exists (checked by _check_references_exist)
            walk(token_name)
        stack.pop()
        visiting.discard(name)
        done.add(name)

    for token_name in graph:
        walk(token_name)


def _max_resolution_depth(config: MatcherConfig) -> int:
    """Maximum depth of a token (leaf = 1). Assumes the graph is acyclic."""
    graph = {
        name: _definition_token_names(token_definition)
        for name, token_definition in config.tokens.items()
    }
    memo: dict[str, int] = {}

    def depth(name: str) -> int:
        if name in memo:
            return memo[name]
        token_names = graph.get(name, ())
        token_depth = (
            1 if not token_names else 1 + max(depth(token_name) for token_name in token_names)
        )
        memo[name] = token_depth
        return token_depth

    return max((depth(name) for name in graph), default=0)


def _check_regexes_compile(config: MatcherConfig) -> None:
    """Each RegexDefinition interpolates (known placeholders), compiles under ``re`` (cf. §8.4)."""
    for name, token_definition in config.tokens.items():
        if not isinstance(token_definition, RegexDefinition):
            continue
        try:
            pattern = interpolate(token_definition.pattern, target=_PROBE_TARGET)
        except InterpolationError as exc:
            raise MatchingConfigError(f"token {name!r}: invalid interpolation: {exc}") from exc
        if "i" in token_definition.flags:
            pattern = "(?i)" + pattern
        try:
            re.compile(pattern, re.ASCII)
        except re.error as exc:
            raise MatchingConfigError(f"token {name!r}: regex not compilable: {exc}") from exc


def validate_config(config: MatcherConfig, *, max_depth: int = _DEFAULT_MAX_DEPTH) -> None:
    """Validates the graph (references, DAG, depth) and the regexes (cf. spec §8.4).

    Raises :class:`UnknownTokenError`, :class:`CycleError`, :class:`DepthExceededError`
    or :class:`MatchingConfigError` (regex/interpolation). To be called after schema parsing.
    """
    _check_references_exist(config)
    _check_vetoes(config)
    _check_overrides_only_on_coverage(config)
    _check_acyclic(config, max_depth=max_depth)
    depth = _max_resolution_depth(config)
    if depth > max_depth:
        raise DepthExceededError(
            f"resolution depth {depth} > max {max_depth} (default {_DEFAULT_MAX_DEPTH})"
        )
    _check_regexes_compile(config)


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

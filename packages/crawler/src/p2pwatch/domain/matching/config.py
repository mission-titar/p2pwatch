"""Matching-engine config model: tagged union of frozen dataclasses.

Represents the §8.3 grammar (named leaf + composite tokens, operands at point of use,
rules). PURE domain: no I/O, no YAML library import. Built from ``matcher.yml`` by the config
adapter.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from p2pwatch.domain.matching.decision_tier import DecisionTier

# --- LEAF token definitions (4 types, cf. spec §8.2) ---

DEFAULT_REGEX_FLAGS = "i"
DEFAULT_MIN_SIMILARITY = 0.85


@dataclass(kw_only=True, frozen=True)
class KeywordDefinition:
    """``{ keyword: "mission titar" }``: phrase searched as a contiguous subsequence."""

    phrase: str


@dataclass(kw_only=True, frozen=True)
class RegexDefinition:
    """``{ regex: "...", flags: "i" }``: fragments expanded at parse, interpolated per target."""

    pattern: str
    flags: str = DEFAULT_REGEX_FLAGS


@dataclass(kw_only=True, frozen=True)
class CoverageDefinition:
    """``{ coverage: title, min_coverage: 0.6, min_similarity: 0.85 }``: fuzzy word coverage.

    ``reference`` is the config keyword (``title`` = the target's title); bound to
    ``target.title`` at resolution. ``min_coverage``/``min_similarity`` overridable at point
    of use.
    """

    reference: str
    min_coverage: float
    min_similarity: float = DEFAULT_MIN_SIMILARITY


@dataclass(kw_only=True, frozen=True)
class AttributeBetweenDefinition:
    """``{ attr_between: size_mib, min: 30, max: 600 }``: bound on a numeric attribute."""

    attr: str
    min_bound: float | None = None
    max_bound: float | None = None


# --- COMPOSITE defs / token expressions (cf. spec §8.3: all/any/not) ---
# Reused in three contexts: named composite token, rule body, inline token expression
# `{expression}`. Operands mix bare names, TokenReference, and inline token expressions.

# PEP 695 type alias (`type ...`), lazily evaluated: referencing TokenReference, AllDefinition,
# AnyDefinition and NotDefinition (defined below and mutually recursive) is therefore valid,
# and mypy --strict resolves the recursion.
type Operand = str | TokenReference | AllDefinition | AnyDefinition | NotDefinition


@dataclass(kw_only=True, frozen=True)
class AllDefinition:
    """``all: [operand, ...]``: conjunction."""

    operands: tuple[Operand, ...]


@dataclass(kw_only=True, frozen=True)
class AnyDefinition:
    """``any: [operand, ...]``: disjunction."""

    operands: tuple[Operand, ...]


@dataclass(kw_only=True, frozen=True)
class NotDefinition:
    """``not: operand``: negation of a single operand."""

    operand: Operand


@dataclass(kw_only=True, frozen=True)
class TokenReference:
    """Operand at point of use ``{ token: name, min_coverage?, min_similarity? }`` (EBNF §8.3).

    References a named token; non-null ``min_coverage``/``min_similarity`` override the ones of a
    ``coverage`` token (and ONLY coverage, validated at load time).
    """

    name: str
    min_coverage: float | None = None
    min_similarity: float | None = None


# Union of token definitions nameable in the `tokens` table.
TokenDefinition = (
    KeywordDefinition
    | RegexDefinition
    | CoverageDefinition
    | AttributeBetweenDefinition
    | AllDefinition
    | AnyDefinition
    | NotDefinition
)

# A rule body / inline operand `{expression}` is a token expression.
TokenExpression = AllDefinition | AnyDefinition | NotDefinition

# What a rule's win pins: one segment, the whole episode, nothing.
type Scope = Literal["segment", "episode", "unattributed"]


@dataclass(kw_only=True, frozen=True)
class Rule:
    """Ordered rule: ``{ name, tier, scope, <expression> }`` (cf. spec §8.3)."""

    name: str
    tier: DecisionTier
    scope: Scope
    expression: TokenExpression


@dataclass(kw_only=True, frozen=True)
class MatcherConfig:
    """Validated matcher config: named tokens, file-level vetoes (token names), ordered rules."""

    tokens: Mapping[str, TokenDefinition] = field(default_factory=dict)
    rules: tuple[Rule, ...] = ()
    vetoes: tuple[str, ...] = ()

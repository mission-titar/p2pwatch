"""Matching-engine config model: tagged union of frozen dataclasses.

Represents the §8.3 grammar (named leaf + composite tokens, operands at point of use,
rules). PURE domain: no I/O, no YAML library import. Construction from parsed YAML
(dict/list) is done by ``validation.py``.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

# --- LEAF token definitions (4 types, cf. spec §8.2) ---


@dataclass(frozen=True)
class KeywordDefinition:
    """``{ keyword: "mission titar" }``: phrase searched as a contiguous subsequence."""

    phrase: str


@dataclass(frozen=True)
class RegexDefinition:
    """``{ regex: "...", flags: "i" }``: fragments expanded at parse, interpolated per target."""

    pattern: str
    flags: str = "i"


@dataclass(frozen=True)
class CoverageDefinition:
    """``{ coverage: title, min_coverage: 0.6, min_similarity: 0.85 }``: fuzzy word coverage.

    ``reference`` is the config keyword (``title`` = the target's title); bound to
    ``target.title`` at resolution. ``min_coverage``/``min_similarity`` overridable at point
    of use.
    """

    reference: str
    min_coverage: float
    min_similarity: float = 0.85


@dataclass(frozen=True)
class AttributeBetweenDefinition:
    """``{ attr_between: size_mib, min: 30, max: 600 }``: bound on a numeric attribute."""

    attr: str
    min_bound: float | None = None
    max_bound: float | None = None


# --- COMPOSITE defs / conditions (cf. spec §8.3: all/any/not) ---
# Reused in three contexts: named composite token, rule body, inline condition
# `{condition}`. Operands mix bare names, TokenReference, and inline conditions.

# PEP 695 type alias (`type ...`), lazily evaluated: referencing TokenReference, AllDefinition,
# AnyDefinition and NotDefinition (defined below and mutually recursive) is therefore valid,
# and mypy --strict resolves the recursion.
type Operand = str | TokenReference | AllDefinition | AnyDefinition | NotDefinition


@dataclass(frozen=True)
class AllDefinition:
    """``all: [operand, ...]``: conjunction."""

    operands: tuple[Operand, ...]


@dataclass(frozen=True)
class AnyDefinition:
    """``any: [operand, ...]``: disjunction."""

    operands: tuple[Operand, ...]


@dataclass(frozen=True)
class NotDefinition:
    """``not: operand``: negation of a single operand."""

    operand: Operand


@dataclass(frozen=True)
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

# A rule body / inline operand `{condition}` is a composite condition.
Condition = AllDefinition | AnyDefinition | NotDefinition

# Closed set of tiers (cf. spec §8.3 EBNF: tier).
TIERS: frozenset[str] = frozenset({"catalog", "notify", "download"})

# Tier rank (spec §8.5: "highest tier, download>notify>catalog"). Higher integer =
# STRONGER tier. Source of truth shared by ``engine.MatchingEngine`` (best-decision
# selection) AND ``p2pwatch.domain.coverage`` (display: strongest tier → best
# coverage). Without this sharing, the webui reinvented its own rank with a divergent
# convention: a 4th tier or a rename would have silently skewed the display.
# Tested invariant: ``set(TIER_RANK) == TIERS``.
TIER_RANK: dict[str, int] = {"catalog": 0, "notify": 1, "download": 2}


# Closed set of rule scopes: what a rule's win pins (one segment, the whole episode, nothing).
SCOPES: frozenset[str] = frozenset({"segment", "episode", "unattributed"})


@dataclass(frozen=True)
class Rule:
    """Ordered rule: ``{ name, tier, scope, <condition> }`` (cf. spec §8.3)."""

    name: str
    tier: str
    scope: str
    condition: Condition


@dataclass(frozen=True)
class MatcherConfig:
    """Validated matcher config: named tokens, file-level vetoes (token names), ordered rules."""

    tokens: Mapping[str, TokenDefinition] = field(default_factory=dict)
    rules: tuple[Rule, ...] = ()
    vetoes: tuple[str, ...] = ()

"""Per-target construction of matcher trees (cf. spec §8.5, construction part).

PURE domain. From a VALIDATED :class:`MatcherConfig` (DAG/depth/RE2 guaranteed by
``validation.validate_config``) and a :class:`TargetSegment`, builds the :class:`Matcher`
tree of each named token and each rule. Regexes are interpolated and compiled PER TARGET;
coverages bound to ``target.title`` (with overrides at point of use); keyword/attr_between
are static.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import assert_never

from catalog_matching.domain.combinators import (
    AllMatcher,
    AnyMatcher,
    Matcher,
    NotMatcher,
)
from catalog_matching.domain.config import (
    AllDefinition,
    AnyDefinition,
    AttributeBetweenDefinition,
    CoverageDefinition,
    KeywordDefinition,
    MatcherConfig,
    NotDefinition,
    Operand,
    RegexDefinition,
    Rule,
    TokenDefinition,
    TokenReference,
)
from catalog_matching.domain.interpolation import interpolate
from catalog_matching.domain.matchers import (
    AttributeBetweenMatcher,
    CoverageMatcher,
    KeywordMatcher,
    RegexMatcher,
)
from catalog_matching.domain.models import TargetSegment

# Config keyword designating the target's title as the coverage reference (§8.5).
_TITLE_KEYWORD = "title"


@dataclass(frozen=True)
class ResolvedTarget:
    """Matcher trees built for a target: named tokens + rules, by name."""

    target: TargetSegment
    matcher_by_token_name: Mapping[str, Matcher]
    matcher_by_rule_name: Mapping[str, Matcher]


class MatcherResolver:
    """Builds the :class:`Matcher` trees of a validated config, per target."""

    def __init__(self, config: MatcherConfig) -> None:
        self.config = config

    def resolve_token(
        self,
        name: str,
        target: TargetSegment,
        min_coverage_override: float | None = None,
        min_similarity_override: float | None = None,
    ) -> Matcher:
        """Builds the matcher of token ``name`` for ``target`` (coverage overrides)."""
        return self._build_def(
            self.config.tokens[name], target, min_coverage_override, min_similarity_override
        )

    def resolve_rule(self, rule: Rule, target: TargetSegment) -> Matcher:
        """Builds the matcher of a rule's condition for ``target``."""
        return self._build_def(rule.condition, target, None, None)

    def resolve_target(self, target: TargetSegment) -> ResolvedTarget:
        """Builds all the trees (tokens + rules) for ``target``."""
        tokens = {name: self.resolve_token(name, target) for name in self.config.tokens}
        rules = {rule.name: self.resolve_rule(rule, target) for rule in self.config.rules}
        return ResolvedTarget(
            target=target, matcher_by_token_name=tokens, matcher_by_rule_name=rules
        )

    def _build_operand(
        self,
        operand: Operand,
        target: TargetSegment,
    ) -> Matcher:
        if isinstance(operand, str):
            return self.resolve_token(operand, target)
        if isinstance(operand, TokenReference):
            return self.resolve_token(
                operand.name, target, operand.min_coverage, operand.min_similarity
            )
        return self._build_def(operand, target, None, None)

    def _build_def(
        self,
        token_def: TokenDefinition,
        target: TargetSegment,
        min_coverage_override: float | None,
        min_similarity_override: float | None,
    ) -> Matcher:
        match token_def:
            case KeywordDefinition(phrase=phrase):
                return KeywordMatcher(phrase)
            case RegexDefinition(pattern=pattern, flags=flags):
                return RegexMatcher(interpolate(pattern, target), flags=flags)
            case CoverageDefinition(
                reference=reference, min_coverage=min_coverage, min_similarity=min_similarity
            ):
                reference_text = target.title if reference == _TITLE_KEYWORD else reference
                return CoverageMatcher(
                    reference=reference_text,
                    min_coverage=(
                        min_coverage if min_coverage_override is None else min_coverage_override
                    ),
                    min_similarity=(
                        min_similarity
                        if min_similarity_override is None
                        else min_similarity_override
                    ),
                )
            case AttributeBetweenDefinition(attr=attr, min_bound=min_bound, max_bound=max_bound):
                return AttributeBetweenMatcher(attr, min_bound=min_bound, max_bound=max_bound)
            case AllDefinition(operands=operands):
                return AllMatcher(tuple(self._build_operand(op, target) for op in operands))
            case AnyDefinition(operands=operands):
                return AnyMatcher(tuple(self._build_operand(op, target) for op in operands))
            case NotDefinition(operand=operand):
                return NotMatcher(self._build_operand(operand, target))
            case _:  # pragma: no cover - exhaustive (mypy proves it via assert_never)
                assert_never(token_def)

"""Matching EVALUATION engine (cf. spec §8.5, evaluation part).

PURE domain. Takes an already-validated :class:`MatcherConfig` (Plan 2b) and some
:class:`TargetSegment`s, pre-resolves the per-target matcher trees once at construction
(via :class:`MatcherResolver`), then produces an IN-MEMORY decision for a
:class:`FileCandidate`. NO I/O, NO logging, NO DB: the "explainability logged at DEBUG" of
§8.5 = the engine RETURNS an explainable result; logging is the job of an adapter in a
later plan.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import NamedTuple

from catalog_matching.domain.combinators import Matcher
from catalog_matching.domain.config import MatcherConfig
from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.identifiers import TargetId
from catalog_matching.domain.matchers import CoverageMatcher
from catalog_matching.domain.models import FileCandidate, TargetSegment
from catalog_matching.domain.resolver import MatcherResolver, ResolvedTarget


@dataclass(frozen=True)
class Explanation:
    """Why this decision (cf. spec §8.5): fired rules, tokens and vetoes, coverage values.

    Concerns ONE target, over the candidates given: a rule, token or veto is listed when true
    on at least one candidate. ``rules_fired`` in config order; ``tokens_matched`` and
    ``vetoes_fired`` sorted; ``coverage_values`` holds EVERY coverage token with its best
    value, sorted by name.
    """

    target_id: TargetId
    rules_fired: tuple[str, ...]
    tokens_matched: tuple[str, ...]
    coverage_values: tuple[tuple[str, float], ...]
    vetoes_fired: tuple[str, ...] = ()


@dataclass(frozen=True)
class MatchDecision:
    """File decision (cf. spec §8.5). Carries the 3 match_decisions columns (§11).

    ``target_id``/``rule_name``/``tier`` = exactly the columns that ``match_decisions``
    will persist (§11). ``decided_at``/``node_id``/``file_id`` are NOT here: they are
    persistence columns (instant + identity + content key) the crawler adds when it records
    the decision. ``explanation`` carries the explainability (§8.5).
    """

    target_id: TargetId
    rule_name: str
    tier: DecisionTier
    explanation: Explanation


@dataclass(frozen=True)
class DecisionRecord:
    """The 3 COMPARABLE columns of a persisted decision, without the runtime explainability.

    This is exactly what ``match_decisions`` stores (§11), ``target_id``/``rule_name``/
    ``tier``, read back for anti-redundancy (orchestration spec §3: only re-``record_decision``
    if the verdict CHANGES). Deliberately distinct from :class:`MatchDecision`: the read
    cannot reconstruct the ``explanation`` (not persisted), and two ``DecisionRecord``s are
    equal iff their three fields are equal (frozen dataclass → field-by-field ``==``).
    """

    target_id: TargetId
    rule_name: str
    tier: DecisionTier


def to_record(decision: MatchDecision) -> DecisionRecord:
    """Projects a :class:`MatchDecision` (just reached) onto its comparable form.

    Lets the application compare the FRESH verdict against the last known ``DecisionRecord``
    without handling the ``explanation`` (orchestration spec §3, anti-redundancy).
    """
    return DecisionRecord(
        target_id=decision.target_id, rule_name=decision.rule_name, tier=decision.tier
    )


class _RuleHit(NamedTuple):
    """The first rule ``candidate`` fires for one resolved target."""

    resolved: ResolvedTarget
    rule_index: int
    rule_name: str
    tier: DecisionTier
    candidate: FileCandidate


def _first_matching_rule(
    config: MatcherConfig,
    resolved: ResolvedTarget,
    candidate: FileCandidate,
) -> tuple[int, str, DecisionTier] | None:
    """1st rule true for (candidate, resolved target) → ``(index, name, tier)`` (§8.5).

    Walks ``config.rules`` IN ORDER (index = position = priority); for each rule, evaluates
    the already-built tree ``resolved.matcher_by_rule_name[rule.name]``. Returns the 1st
    match; ``None`` if no rule matches (the target contributes nothing).
    """
    for index, rule in enumerate(config.rules):
        if resolved.matcher_by_rule_name[rule.name].matches(candidate):
            return (index, rule.name, rule.tier)
    return None


def _explain(
    config: MatcherConfig,
    resolved: ResolvedTarget,
    candidates: Sequence[FileCandidate],
) -> Explanation:
    """Builds the explanation of ``resolved`` over ``candidates`` (cf. :class:`Explanation`)."""

    def fired(matcher: Matcher) -> bool:
        return any(matcher.matches(candidate) for candidate in candidates)

    matcher_by_token_name = resolved.matcher_by_token_name
    return Explanation(
        target_id=resolved.target.target_id,
        rules_fired=tuple(
            rule.name for rule in config.rules if fired(resolved.matcher_by_rule_name[rule.name])
        ),
        tokens_matched=tuple(
            sorted(
                token_name
                for token_name, matcher in matcher_by_token_name.items()
                if fired(matcher)
            )
        ),
        coverage_values=tuple(
            (
                token_name,
                max((matcher.coverage(candidate) for candidate in candidates), default=0.0),
            )
            for token_name, matcher in sorted(matcher_by_token_name.items())
            if isinstance(matcher, CoverageMatcher)
        ),
        vetoes_fired=tuple(
            sorted(veto for veto in config.vetoes if fired(matcher_by_token_name[veto]))
        ),
    )


class MatchingEngine:
    """Pure facade of the evaluation engine (cf. spec §8.5). Pre-resolves targets once.

    Brute-force §8.5: each file is evaluated against ALL targets (no funnel heuristic). The
    matcher trees (regexes interpolated+compiled per target) are built ONCE at construction.
    ``max_filename_length`` bounds the filename length before matching (§8.5/§14): a longer
    filename's candidate is discarded (``[]``).
    """

    def __init__(
        self,
        config: MatcherConfig,
        targets: Sequence[TargetSegment],
        *,
        max_filename_length: int,
    ) -> None:
        self._config = config
        self._max_filename_length = max_filename_length
        resolver = MatcherResolver(config)
        self._resolved: tuple[ResolvedTarget, ...] = tuple(
            resolver.resolve_target(target) for target in targets
        )
        self._resolved_by_target: dict[TargetId, ResolvedTarget] = {
            r.target.target_id: r for r in self._resolved
        }

    def target(self, target_id: TargetId) -> TargetSegment | None:
        """The target segment of ``target_id``, or ``None`` if unknown."""
        resolved = self._resolved_by_target.get(target_id)
        return None if resolved is None else resolved.target

    def explain(
        self, candidates: Iterable[FileCandidate], target_id: TargetId
    ) -> Explanation | None:
        """Explains target ``target_id`` over every candidate of one file; ``None`` if unknown.

        Over-long filenames are skipped, as in :meth:`evaluate_file`.
        """
        resolved = self._resolved_by_target.get(target_id)
        if resolved is None:
            return None
        return _explain(self._config, resolved, self._matchable_candidates(candidates))

    def evaluate_file(self, candidates: Iterable[FileCandidate]) -> list[MatchDecision]:
        """All decisions for ONE file, one candidate per filename; ``[]`` = discard.

        A target is skipped when any veto matches any candidate (over-long filenames skipped).
        Per surviving target, the best rule over all candidates (min-key below).
        Hits of a ``segment`` or ``episode`` scoped rule fan out per episode: a
        segment-scoped hit on any segment of an episode emits only those segments,
        otherwise the episode-scoped hits emit every segment (spec §3). With none, the
        single-winner min-key over ALL hits yields one ``unattributed`` decision, or ``[]``.
        """
        matchable_candidates = self._matchable_candidates(candidates)
        best_by_target_id: dict[TargetId, _RuleHit] = {}
        for resolved in self._resolved:
            if self._vetoed(resolved, matchable_candidates):
                continue
            for candidate in matchable_candidates:
                outcome = _first_matching_rule(self._config, resolved, candidate)
                if outcome is None:
                    continue
                index, rule_name, tier = outcome
                target_id = resolved.target.target_id
                current = best_by_target_id.get(target_id)
                if current is None or (-tier.rank, index) < (
                    -current.tier.rank,
                    current.rule_index,
                ):
                    best_by_target_id[target_id] = _RuleHit(
                        resolved, index, rule_name, tier, candidate
                    )
        hits = list(best_by_target_id.values())
        attributable = self._fan_out(hits)
        if attributable:
            return attributable
        return self._single_winner(hits)

    def _matchable_candidates(self, candidates: Iterable[FileCandidate]) -> list[FileCandidate]:
        return [
            candidate
            for candidate in candidates
            if len(candidate.filename) <= self._max_filename_length
        ]

    def _vetoed(self, resolved: ResolvedTarget, candidates: Sequence[FileCandidate]) -> bool:
        """True when any veto matches any candidate: the target is out for the whole file."""
        return any(
            resolved.matcher_by_token_name[veto].matches(candidate)
            for veto in self._config.vetoes
            for candidate in candidates
        )

    def _fan_out(self, hits: list[_RuleHit]) -> list[MatchDecision]:
        """Selects the emitted segments from the segment/episode scoped hits (spec §3/§4)."""
        rules = self._config.rules
        hits_by_episode: dict[int, list[_RuleHit]] = {}
        for hit in hits:
            if rules[hit.rule_index].scope == "unattributed":
                continue
            hits_by_episode.setdefault(hit.resolved.target.absolute_number, []).append(hit)
        emitted: list[_RuleHit] = []
        for group in hits_by_episode.values():
            segment_level = [hit for hit in group if rules[hit.rule_index].scope == "segment"]
            emitted.extend(segment_level or group)
        emitted.sort(key=lambda hit: hit.resolved.target.target_id)
        return [self._decision(hit) for hit in emitted]

    def _single_winner(self, hits: list[_RuleHit]) -> list[MatchDecision]:
        """Existing min-key: one catch-all decision over ALL hits, or ``[]`` (spec §4 step 6).

        Key = (highest tier, smallest rule index, smallest ``target_id``); ``target_id`` is
        unique, so the key is a strict total order -> a unique, target-order-independent winner.
        """
        best_key: tuple[int, int, str] | None = None
        best_hit: _RuleHit | None = None
        for hit in hits:
            key = (-hit.tier.rank, hit.rule_index, hit.resolved.target.target_id)
            if best_key is None or key < best_key:
                best_key = key
                best_hit = hit
        if best_hit is None:
            return []
        return [self._decision(best_hit)]

    def _decision(self, hit: _RuleHit) -> MatchDecision:
        return MatchDecision(
            target_id=hit.resolved.target.target_id,
            rule_name=hit.rule_name,
            tier=hit.tier,
            explanation=_explain(self._config, hit.resolved, (hit.candidate,)),
        )

from random import Random

from catalog_matching.domain.decision_tier import DecisionTier
from p2pwatch.domain.file_target_decision import DatedDecision, FileTargetDecision, Retraction
from tests.support.domain.file_target_decision import (
    draw_dated_decision,
    draw_decision_record,
    draw_target_ids,
)
from tests.support.domain.observation import draw_file
from tests.support.draws import draw_instant

_SEEDS = range(1000)


def _drawn(seed: int) -> DatedDecision[FileTargetDecision]:
    randomness = Random(seed)
    return draw_dated_decision(
        randomness,
        file=draw_file(randomness),
        decision=draw_decision_record(randomness, tier=DecisionTier.DOWNLOAD),
    )


def test_the_texts_of_a_drawn_decision_differ() -> None:
    for dated_decision in map(_drawn, _SEEDS):
        decision = dated_decision.decision
        assert not isinstance(decision, Retraction)
        texts = (
            dated_decision.file.native_id,
            decision.target_id,
            decision.rule_name,
            dated_decision.node_id,
        )
        # Distinct by construction: each text takes a length of its own.
        assert len({len(text) for text in texts}) == len(texts), texts


def test_drawn_target_ids_are_distinct_and_ascending() -> None:
    for seed in _SEEDS:
        target_ids = draw_target_ids(Random(seed), count=3)
        assert list(target_ids) == sorted(set(target_ids))
        assert len(target_ids) == 3


def test_drawn_target_ids_are_never_empty() -> None:
    assert all(draw_target_ids(Random(seed), count=1)[0] for seed in _SEEDS)


def test_a_drawn_decision_keeps_what_its_test_relates() -> None:
    randomness = Random(0)
    file = draw_file(randomness)
    [target_id] = draw_target_ids(randomness, count=1)
    decided_at = draw_instant(randomness)
    record = draw_decision_record(randomness, tier=DecisionTier.NOTIFY, target_id=target_id)
    dated_decision = draw_dated_decision(
        randomness, file=file, decision=record, decided_at=decided_at
    )
    assert (record.target_id, record.tier) == (target_id, DecisionTier.NOTIFY)
    assert dated_decision == DatedDecision(
        file=file, decision=record, decided_at=decided_at, node_id=dated_decision.node_id
    )


def test_the_same_seed_draws_the_same_decision() -> None:
    assert _drawn(7) == _drawn(7)

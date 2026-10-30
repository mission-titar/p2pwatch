from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord
from catalog_matching.domain.identifiers import TargetId
from p2pwatch.domain.file_target_decision import FileTargetDecision, Retraction, records_to_write


def _record(target_id: TargetId, tier: DecisionTier = DecisionTier.DOWNLOAD) -> DecisionRecord:
    return DecisionRecord(target_id=target_id, rule_name="id_segment_exact", tier=tier)


def test_retractions_are_equal_when_their_targets_are() -> None:
    assert Retraction(TargetId("062A")) == Retraction(TargetId("062A"))
    assert Retraction(TargetId("062A")) != Retraction(TargetId("062B"))


def test_a_fresh_record_equal_to_the_persisted_one_is_not_written() -> None:
    assert (
        records_to_write(
            [_record(TargetId("062A"))], persisted={TargetId("062A"): _record(TargetId("062A"))}
        )
        == ()
    )


def test_a_fresh_record_is_written_when_new_changed_or_over_a_retraction() -> None:
    fresh = [
        _record(TargetId("062A")),
        _record(TargetId("062B"), DecisionTier.NOTIFY),
        _record(TargetId("062C")),
    ]
    persisted: dict[TargetId, FileTargetDecision] = {
        TargetId("062B"): _record(TargetId("062B")),
        TargetId("062C"): Retraction(TargetId("062C")),
    }
    assert records_to_write(fresh, persisted=persisted) == tuple(fresh)


def test_a_persisted_target_out_of_the_fresh_ones_is_retracted_once() -> None:
    persisted: dict[TargetId, FileTargetDecision] = {
        TargetId("063B"): _record(TargetId("063B")),
        TargetId("063A"): _record(TargetId("063A")),
        TargetId("063C"): Retraction(TargetId("063C")),
    }
    assert records_to_write([], persisted=persisted) == (
        Retraction(TargetId("063A")),
        Retraction(TargetId("063B")),
    )


def test_the_fresh_records_come_before_the_retractions() -> None:
    written = records_to_write(
        [_record(TargetId("062A"))], persisted={TargetId("001A"): _record(TargetId("001A"))}
    )
    assert written == (_record(TargetId("062A")), Retraction(TargetId("001A")))

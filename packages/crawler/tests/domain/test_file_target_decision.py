from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord
from p2pwatch.domain.file_target_decision import FileTargetDecision, Retraction, records_to_write


def _record(target_id: str, tier: DecisionTier = DecisionTier.DOWNLOAD) -> DecisionRecord:
    return DecisionRecord(target_id, "id_segment_exact", tier)


def test_retractions_are_equal_when_their_targets_are() -> None:
    assert Retraction("062A") == Retraction("062A")
    assert Retraction("062A") != Retraction("062B")


def test_a_fresh_record_equal_to_the_persisted_one_is_not_written() -> None:
    assert records_to_write([_record("062A")], {"062A": _record("062A")}) == ()


def test_a_fresh_record_is_written_when_new_changed_or_over_a_retraction() -> None:
    fresh = [_record("062A"), _record("062B", DecisionTier.NOTIFY), _record("062C")]
    persisted: dict[str, FileTargetDecision] = {"062B": _record("062B"), "062C": Retraction("062C")}
    assert records_to_write(fresh, persisted) == tuple(fresh)


def test_a_persisted_target_out_of_the_fresh_ones_is_retracted_once() -> None:
    persisted: dict[str, FileTargetDecision] = {
        "063B": _record("063B"),
        "063A": _record("063A"),
        "063C": Retraction("063C"),
    }
    assert records_to_write([], persisted) == (Retraction("063A"), Retraction("063B"))


def test_the_fresh_records_come_before_the_retractions() -> None:
    written = records_to_write([_record("062A")], {"001A": _record("001A")})
    assert written == (_record("062A"), Retraction("001A"))

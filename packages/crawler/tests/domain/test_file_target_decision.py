from p2pwatch.domain.file_target_decision import Retraction


def test_retractions_are_equal_when_their_targets_are() -> None:
    assert Retraction("062A") == Retraction("062A")
    assert Retraction("062A") != Retraction("062B")

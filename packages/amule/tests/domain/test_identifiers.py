from p2pwatch_amule.domain.identifiers import Gid, Uid


def _uid(uid: Uid) -> int:
    return uid


def _gid(gid: Gid) -> int:
    return gid


def test_a_bare_int_is_neither_a_uid_nor_a_gid() -> None:
    """Each ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _uid(1000) == 1000  # type: ignore[arg-type]
    assert _gid(1001) == 1001  # type: ignore[arg-type]


def test_a_uid_and_a_gid_are_refused_for_each_other() -> None:
    """Each ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _uid(Gid(1001)) == 1001  # type: ignore[arg-type]
    assert _gid(Uid(1000)) == 1000  # type: ignore[arg-type]

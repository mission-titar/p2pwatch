from catalog_matching.domain.identifiers import TargetId


def _target_id(target_id: TargetId) -> str:
    return target_id


def test_a_bare_str_is_no_target_id() -> None:
    """The ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _target_id("62a") == "62a"  # type: ignore[arg-type]

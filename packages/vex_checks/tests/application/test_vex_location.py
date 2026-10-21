"""vex_location: where a check's problems point, the VEX relative to the repository's root."""

from pathlib import PurePath

from vex_checks.application.vex_location import vex_location


def test_a_vex_inside_the_repository_is_located_relative_to_its_root() -> None:
    vex_path = PurePath("/repo/security/amule.vex.openvex.json")

    assert vex_location(vex_path, PurePath("/repo")) == "security/amule.vex.openvex.json"


def test_a_vex_outside_the_repository_is_located_at_its_path_as_given() -> None:
    vex_path = PurePath("/tmp/vex.openvex.json")

    assert vex_location(vex_path, PurePath("/repo")) == "/tmp/vex.openvex.json"

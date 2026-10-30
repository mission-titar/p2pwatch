from pathlib import Path

import pytest

from p2pwatch.adapters.driven.config.yaml_loader import load_yaml
from p2pwatch.domain.broken_input_error import BrokenInputError


def test_load_yaml_reads_mapping(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("tokens:\n  keroro: { keyword: keroro }\n", encoding="utf-8")
    document = load_yaml(path)
    assert document == {"tokens": {"keroro": {"keyword": "keroro"}}}


def test_load_yaml_parses_nested_episode_mapping(tmp_path: Path) -> None:
    path = tmp_path / "t.yaml"
    path.write_text(
        "episodes:\n  - { season: 2, seasonal_number: 11, absolute_number: 62 }\n",
        encoding="utf-8",
    )
    document = load_yaml(path)
    assert document["episodes"][0]["absolute_number"] == 62


@pytest.mark.parametrize(("text", "root_type"), [("- a\n- list\n", "list"), ("", "NoneType")])
def test_a_root_that_is_no_mapping_is_a_broken_input_naming_the_file(
    *, tmp_path: Path, text: str, root_type: str
) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(BrokenInputError) as raised:
        load_yaml(path)
    assert str(raised.value) == f"{path}: mapping expected at its root, got {root_type}"


def test_a_missing_file_is_a_broken_input_naming_the_file(tmp_path: Path) -> None:
    path = tmp_path / "does_not_exist.yaml"
    with pytest.raises(BrokenInputError) as raised:
        load_yaml(path)
    assert str(raised.value) == f"{path}: No such file or directory"


def test_a_file_that_is_not_utf8_is_a_broken_input_naming_the_file(tmp_path: Path) -> None:
    path = tmp_path / "latin1.yaml"
    path.write_bytes("titre: épisode\n".encode("latin-1"))
    with pytest.raises(BrokenInputError) as raised:
        load_yaml(path)
    assert str(raised.value) == f"{path}: not UTF-8"


def test_a_malformed_yaml_is_a_broken_input_on_one_line(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("a: [1, 2\n", encoding="utf-8")  # unclosed bracket
    with pytest.raises(BrokenInputError) as raised:
        load_yaml(path)
    assert str(raised.value).startswith(f"{path}: invalid YAML: while parsing a flow sequence ")
    assert "\n" not in str(raised.value)

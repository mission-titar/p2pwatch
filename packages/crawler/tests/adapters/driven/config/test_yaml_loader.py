from pathlib import Path

import pytest

from p2pwatch.adapters.driven.config.yaml_loader import load_yaml
from p2pwatch.domain.broken_input_error import BrokenInputError
from p2pwatch.domain.config_problem import ConfigProblem


def test_load_yaml_reads_mapping(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("tokens:\n  keroro: { keyword: keroro }\n", encoding="utf-8")
    document = load_yaml(path).document
    assert document == {"tokens": {"keroro": {"keyword": "keroro"}}}


def test_load_yaml_parses_nested_episode_mapping(tmp_path: Path) -> None:
    path = tmp_path / "t.yaml"
    path.write_text(
        "episodes:\n  - { season: 2, seasonal_number: 11, absolute_number: 62 }\n",
        encoding="utf-8",
    )
    document = load_yaml(path).document
    assert document["episodes"][0]["absolute_number"] == 62


@pytest.mark.parametrize(("text", "root_type"), [("- a\n- list\n", "list"), ("", "NoneType")])
def test_a_root_that_is_no_mapping_is_a_broken_input(
    *, tmp_path: Path, text: str, root_type: str
) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(BrokenInputError) as raised:
        load_yaml(path)
    assert raised.value.reason == f"mapping expected at its root, got {root_type}"


def test_a_missing_file_is_a_broken_input(tmp_path: Path) -> None:
    path = tmp_path / "does_not_exist.yaml"
    with pytest.raises(BrokenInputError) as raised:
        load_yaml(path)
    assert raised.value.reason == "No such file or directory"


def test_a_file_that_is_not_utf8_is_a_broken_input(tmp_path: Path) -> None:
    path = tmp_path / "latin1.yaml"
    path.write_bytes("titre: épisode\n".encode("latin-1"))
    with pytest.raises(BrokenInputError) as raised:
        load_yaml(path)
    assert raised.value.reason == "not UTF-8"


def test_a_malformed_yaml_is_a_broken_input_on_one_line(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("a: [1, 2\n", encoding="utf-8")  # unclosed bracket
    with pytest.raises(BrokenInputError) as raised:
        load_yaml(path)
    assert raised.value.reason.startswith("invalid YAML: while parsing a flow sequence ")
    assert "\n" not in raised.value.reason


# A YAML escape counts in UTF-16 units, so a UTF-8 file can spell a surrogate, paired or not.
@pytest.mark.parametrize(
    ("text", "key_path"),
    [
        ('title: "\\ud800"\n', "title"),
        ('title: "\\U0000dfff"\n', "title"),
        ('title: "\\ud83d\\ude00"\n', "title"),
        ('search:\n  keywords: [keroro, "a\\udcffb"]\n', "search.keywords[1]"),
        ('rules:\n  - { name: "\\ud800", tier: catalog }\n', "rules[0].name"),
        ('"\\ud800": x\n', "\\ud800"),
        ('webui:\n  "\\ud800": x\n', "webui.\\ud800"),
        ('"a\\tb\\xe9": { title: "\\ud800" }\n', "a\\tb\xe9.title"),
    ],
)
def test_a_text_that_is_not_utf8_is_a_broken_input_naming_its_key_path(
    *, tmp_path: Path, text: str, key_path: str
) -> None:
    path = tmp_path / "escaped.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(BrokenInputError) as raised:
        load_yaml(path)
    assert raised.value.reason == f"{key_path} is not valid UTF-8"


def test_a_text_beyond_ascii_that_is_valid_utf8_loads_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "unicode.yaml"
    path.write_text(
        'title: "\\U0001F600 \N{REPLACEMENT CHARACTER} \N{GRINNING FACE} \xe9"\n', encoding="utf-8"
    )
    assert load_yaml(path).document == {
        "title": "\N{GRINNING FACE} \N{REPLACEMENT CHARACTER} \N{GRINNING FACE} \xe9"
    }


@pytest.mark.parametrize(
    ("text", "key_path"),
    [
        ("search:\n  keywords: &k [keroro, *k]\n", "search.keywords[1]"),
        ("webui: &w\n  bind: { webui: *w }\n", "webui.bind.webui"),
        ("&root\nwebui: *root\n", "webui"),
    ],
)
def test_an_alias_of_a_value_holding_it_is_a_broken_input_naming_its_key_path(
    *, tmp_path: Path, text: str, key_path: str
) -> None:
    path = tmp_path / "cycle.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(BrokenInputError) as raised:
        load_yaml(path)
    assert raised.value.reason == f"{key_path} refers to a value that holds it"


def test_an_alias_reused_beside_its_anchor_loads(tmp_path: Path) -> None:
    path = tmp_path / "shared.yaml"
    path.write_text("a: &k [keroro]\nb: { c: *k, d: *k }\n", encoding="utf-8")
    assert load_yaml(path).document == {"a": ["keroro"], "b": {"c": ["keroro"], "d": ["keroro"]}}


def test_a_file_with_each_key_written_once_has_no_problem(tmp_path: Path) -> None:
    path = tmp_path / "once.yaml"
    path.write_text("a: 1\nb: { a: 2 }\nc: [{ a: 3 }]\n", encoding="utf-8")
    assert load_yaml(path).problems == ()


def test_each_key_written_twice_is_a_problem_in_the_order_of_its_repeats(
    tmp_path: Path,
) -> None:
    path = tmp_path / "twice.yaml"
    path.write_text(
        "search:\n"
        "  keywords: [keroro]\n"
        "  keywords: [titar]\n"
        "rules:\n"
        "  - { name: a, name: b }\n"
        "search: { keywords: [giroro] }\n",
        encoding="utf-8",
    )

    loaded = load_yaml(path)

    assert loaded.problems == (
        ConfigProblem(
            file_path=path, key="search.keywords", message="written twice, at lines 2 and 3"
        ),
        ConfigProblem(file_path=path, key="rules[0].name", message="written twice on line 5"),
        ConfigProblem(file_path=path, key="search", message="written twice, at lines 1 and 6"),
    )
    assert loaded.document == {"search": {"keywords": ["giroro"]}, "rules": [{"name": "b"}]}


def test_a_key_written_three_times_is_a_problem_per_repeat_naming_the_first_line(
    tmp_path: Path,
) -> None:
    path = tmp_path / "thrice.yaml"
    path.write_text("a: 1\na: 2\na: 3\n", encoding="utf-8")
    assert [problem.message for problem in load_yaml(path).problems] == [
        "written twice, at lines 1 and 2",
        "written twice, at lines 1 and 3",
    ]


def test_two_spellings_of_one_key_are_a_key_written_twice(tmp_path: Path) -> None:
    path = tmp_path / "spellings.yaml"
    path.write_text('episodes:\n  1: a\n  0x1: b\n"c": d\nc: e\n', encoding="utf-8")
    assert [problem.key for problem in load_yaml(path).problems] == ["episodes.1", "c"]


def test_a_key_written_twice_under_an_anchor_is_one_problem_at_the_anchor(tmp_path: Path) -> None:
    path = tmp_path / "anchor.yaml"
    path.write_text("a: &k { b: 1, b: 2 }\nc: *k\nd: { e: *k }\n", encoding="utf-8")
    assert load_yaml(path).problems == (
        ConfigProblem(file_path=path, key="a.b", message="written twice on line 1"),
    )


def test_a_key_a_merge_key_brings_overridden_is_no_key_written_twice(tmp_path: Path) -> None:
    path = tmp_path / "merge.yaml"
    path.write_text("base: &base { a: 1, b: 2 }\nmerged:\n  <<: *base\n  a: 3\n", encoding="utf-8")

    loaded = load_yaml(path)

    assert loaded.problems == ()
    assert loaded.document["merged"] == {"a": 3, "b": 2}


def test_a_key_written_twice_in_a_mapping_a_merge_key_brings_is_a_problem(
    tmp_path: Path,
) -> None:
    path = tmp_path / "merge.yaml"
    path.write_text("merged:\n  <<: { a: 1, a: 2 }\n  b: 3\n", encoding="utf-8")
    assert load_yaml(path).problems == (
        ConfigProblem(file_path=path, key="merged.a", message="written twice on line 2"),
    )


def test_a_key_that_is_a_sequence_is_a_broken_input(tmp_path: Path) -> None:
    path = tmp_path / "sequence_key.yaml"
    path.write_text("? [a]\n: b\n", encoding="utf-8")
    with pytest.raises(BrokenInputError) as raised:
        load_yaml(path)
    assert raised.value.reason.startswith("invalid YAML: while constructing a mapping ")

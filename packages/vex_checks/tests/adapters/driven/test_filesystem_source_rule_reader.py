from pathlib import Path

import pytest

from vex_checks.adapters.driven.filesystem_source_rule_reader import FilesystemSourceRuleReader


def test_read_source_rule_ids_names_each_rule_by_its_file(tmp_path: Path) -> None:
    (tmp_path / "CVE-2025-15366.yml").write_text("id: CVE-2025-15366\nnot: [parsed")
    (tmp_path / "CVE-2025-15367.yml").write_text("language: python\nid: CVE-2025-15367\n")
    (tmp_path / "README.md").write_text("")

    reader = FilesystemSourceRuleReader(rules_directory=tmp_path)

    assert reader.read_source_rule_ids() == {"CVE-2025-15366", "CVE-2025-15367"}


def test_read_source_rule_ids_refuses_a_rule_whose_id_is_not_its_file_name(
    tmp_path: Path,
) -> None:
    (tmp_path / "CVE-2099-0001.yml").write_text("id: CVE-2025-15366\nrule:\n  id: CVE-2099-0001\n")

    reader = FilesystemSourceRuleReader(rules_directory=tmp_path)

    with pytest.raises(ValueError, match=r"CVE-2099-0001\.yml: its id is not CVE-2099-0001"):
        reader.read_source_rule_ids()


def test_read_source_rule_ids_refuses_a_rule_with_no_id(tmp_path: Path) -> None:
    (tmp_path / "CVE-2025-15366.yml").write_text("language: python\n")

    reader = FilesystemSourceRuleReader(rules_directory=tmp_path)

    with pytest.raises(ValueError, match=r"CVE-2025-15366\.yml: its id is not CVE-2025-15366"):
        reader.read_source_rule_ids()


def test_read_source_rule_ids_of_an_absent_directory_raises(tmp_path: Path) -> None:
    reader = FilesystemSourceRuleReader(rules_directory=tmp_path / "absent")

    with pytest.raises(FileNotFoundError):
        reader.read_source_rule_ids()

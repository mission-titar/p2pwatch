from pathlib import Path

import pytest

from vex_checks.adapters.driven.filesystem_source_rule_reader import FilesystemSourceRuleReader


def test_read_source_rule_ids_names_each_rule_by_its_file(tmp_path: Path) -> None:
    (tmp_path / "CVE-2025-15366.yml").write_text("not: [parsed")
    (tmp_path / "CVE-2025-15367.yml").write_text("")
    (tmp_path / "README.md").write_text("")

    reader = FilesystemSourceRuleReader(rules_directory=tmp_path)

    assert reader.read_source_rule_ids() == {"CVE-2025-15366", "CVE-2025-15367"}


def test_read_source_rule_ids_of_an_absent_directory_raises(tmp_path: Path) -> None:
    reader = FilesystemSourceRuleReader(rules_directory=tmp_path / "absent")

    with pytest.raises(FileNotFoundError):
        reader.read_source_rule_ids()

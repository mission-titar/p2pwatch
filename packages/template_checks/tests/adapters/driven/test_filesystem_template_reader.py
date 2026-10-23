import os
import re
from pathlib import Path, PurePath

import pytest

from template_checks.adapters.driven.filesystem_template_reader import FilesystemTemplateReader
from template_checks.domain.broken_input_error import BrokenInputError


def test_read_templates_reads_every_html_under_the_directory_by_its_relative_path(
    tmp_path: Path,
) -> None:
    (tmp_path / "partials").mkdir()
    (tmp_path / "partials" / "row.html").write_text("{{ row.filename }}", encoding="utf-8")
    (tmp_path / "base.html").write_text("<p>« {{ title }} »</p>", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("{{ row.ignored }}", encoding="utf-8")

    text_by_template_path = FilesystemTemplateReader().read_templates(tmp_path)

    assert list(text_by_template_path.items()) == [
        (PurePath("base.html"), "<p>« {{ title }} »</p>"),
        (PurePath("partials/row.html"), "{{ row.filename }}"),
    ]


def test_read_templates_of_a_directory_without_templates_reads_nothing(tmp_path: Path) -> None:
    assert FilesystemTemplateReader().read_templates(tmp_path) == {}


def test_read_templates_of_an_absent_directory_raises_a_broken_input_naming_it(
    tmp_path: Path,
) -> None:
    templates_directory = tmp_path / "absent"

    with pytest.raises(
        BrokenInputError,
        match=f"^{re.escape(str(templates_directory))}: No such file or directory$",
    ):
        FilesystemTemplateReader().read_templates(templates_directory)


def test_read_templates_of_a_file_raises_a_broken_input_naming_it(tmp_path: Path) -> None:
    templates_file = tmp_path / "page.html"
    templates_file.write_text("{{ title }}", encoding="utf-8")

    with pytest.raises(
        BrokenInputError, match=f"^{re.escape(str(templates_file))}: Not a directory$"
    ):
        FilesystemTemplateReader().read_templates(templates_file)


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a directory whatever its mode")
def test_read_templates_under_an_unreadable_directory_raises_a_broken_input_naming_it(
    tmp_path: Path,
) -> None:
    unreadable_directory = tmp_path / "partials"
    unreadable_directory.mkdir()
    (unreadable_directory / "row.html").write_text("{{ row.filename }}", encoding="utf-8")
    unreadable_directory.chmod(0)

    try:
        with pytest.raises(
            BrokenInputError, match=f"^{re.escape(str(unreadable_directory))}: Permission denied$"
        ):
            FilesystemTemplateReader().read_templates(tmp_path)
    finally:
        unreadable_directory.chmod(0o755)


def test_read_templates_of_a_template_it_cannot_open_raises_a_broken_input_naming_it(
    tmp_path: Path,
) -> None:
    dangling_template = tmp_path / "page.html"
    dangling_template.symlink_to(tmp_path / "absent.html")

    with pytest.raises(
        BrokenInputError, match=f"^{re.escape(str(dangling_template))}: No such file or directory$"
    ):
        FilesystemTemplateReader().read_templates(tmp_path)


def test_read_templates_of_a_template_not_in_utf_8_raises_a_broken_input_naming_it(
    tmp_path: Path,
) -> None:
    latin_1_template = tmp_path / "page.html"
    latin_1_template.write_bytes("<p>é</p>".encode("latin-1"))

    with pytest.raises(BrokenInputError, match=f"^{re.escape(str(latin_1_template))}: not UTF-8$"):
        FilesystemTemplateReader().read_templates(tmp_path)

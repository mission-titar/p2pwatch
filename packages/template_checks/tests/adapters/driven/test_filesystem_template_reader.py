from pathlib import Path, PurePath

from template_checks.adapters.driven.filesystem_template_reader import FilesystemTemplateReader


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

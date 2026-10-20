from pathlib import Path, PurePath

from amule_bump.adapters.driven.github_step_output_writer import GitHubStepOutputWriter


def test_write_step_outputs_appends_the_version_and_the_body_s_path(tmp_path: Path) -> None:
    output_path = tmp_path / "output"
    output_path.write_text("earlier=kept\n")
    GitHubStepOutputWriter(output_path).write_step_outputs("3.1.0", PurePath("/tmp/body.md"))
    assert output_path.read_text() == "earlier=kept\nversion=3.1.0\nbody-path=/tmp/body.md\n"

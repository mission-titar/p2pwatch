from pathlib import PurePath

import pytest

from amule_bump.adapters.driven.terminal_step_output_writer import TerminalStepOutputWriter


def test_write_step_outputs_prints_the_version_and_the_body_s_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    TerminalStepOutputWriter().write_step_outputs("3.1.0", PurePath("/tmp/body.md"))
    assert capsys.readouterr().out == "version=3.1.0\nbody-path=/tmp/body.md\n"

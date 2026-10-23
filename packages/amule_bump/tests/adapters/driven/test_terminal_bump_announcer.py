from pathlib import PurePath

import pytest

from amule_bump.adapters.driven.terminal_bump_announcer import TerminalBumpAnnouncer


def test_announce_bump_prints_the_version_and_the_body_s_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    TerminalBumpAnnouncer().announce_bump("3.1.0", PurePath("/tmp/body.md"))
    assert capsys.readouterr().out == "version=3.1.0\nbody-path=/tmp/body.md\n"

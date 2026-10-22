"""The command line, wired to the real adapters and composition."""

import logging
from pathlib import Path

import pytest

from p2pwatch.composition.command_line import build_command_line
from tests.support.adapters.driven.persistence_sqlite.helpers import (
    HASH_A,
    HASH_B,
    count,
    make_catalog,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEPLOY = _REPO_ROOT / "deploy"
_ENV = {"AMULE_API_PASSWORD": "s3cr3t"}


def _run(argv: list[str], cwd: Path) -> int:
    return build_command_line(env=_ENV, cwd=cwd, root_logger=logging.getLogger()).run(argv)


def _paths_argv(*, config: Path, matcher: Path = _DEPLOY / "matcher.yml") -> list[str]:
    targets = _DEPLOY / "targets.yml"
    return ["--config", str(config), "--targets", str(targets), "--matcher", str(matcher)]


def test_crawl_exits_one_on_a_broken_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "crawler.yml"
    broken.write_text("catalog_db_path: c\nlocal_db_path: l\n", encoding="utf-8")

    assert _run(["crawl", *_paths_argv(config=broken)], tmp_path) == 1

    assert capsys.readouterr().err.startswith("Invalid config, refusing to start: ")


def test_validate_config_from_the_repository_root_accepts_the_shipped_config(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _run(["validate-config"], _REPO_ROOT) == 0

    assert capsys.readouterr().out == "Config valid\n"


def test_validate_config_refuses_a_broken_matcher(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken_matcher = tmp_path / "matcher.yml"
    broken_matcher.write_text("tokens: {}\nrules: {}\n", encoding="utf-8")

    argv = ["validate-config", *_paths_argv(config=_DEPLOY / "crawler.yml", matcher=broken_matcher)]
    assert _run(argv, tmp_path) == 1

    assert capsys.readouterr().err.startswith("Invalid config: ")


def test_merge_of_two_catalogs_named_under_cwd_into_a_new_one_holds_both(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    for letter, ed2k in (("a", HASH_A), ("b", HASH_B)):
        make_catalog(tmp_path / f"{letter}.db", {"files": [{"ed2k_hash": ed2k, "size_bytes": 100}]})
    merged = tmp_path / "merged.db"

    with caplog.at_level(logging.INFO):
        # Relative names, under a ``cwd`` that is not the process's own.
        assert _run(["merge", "--output", "merged.db", "a.db", "b.db"], tmp_path) == 0

    assert count(merged, "files") == 2
    done = next(record for record in caplog.records if record.getMessage().startswith("merge done"))
    assert done.name == "p2pwatch.application.merge_catalogs"  # an operator's filters keep it

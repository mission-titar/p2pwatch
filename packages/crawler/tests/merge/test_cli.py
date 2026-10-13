"""TDD tests for the ``python -m p2pwatch.merge`` CLI (safe-by-default), design §6/§7.

We call ``main(argv)`` directly (returns an ``int``); usage/merge errors return ``2`` with a
clear message on ``stderr`` (never a traceback); argparse itself returns ``2`` (via
``SystemExit``) for a parsing error (mutually exclusive/required group).
"""

from pathlib import Path

import pytest

from p2pwatch.merge.__main__ import main

from .helpers import HASH_A, HASH_B, count, make_catalog


def _seed(path: Path, letter: str) -> Path:
    ed2k = HASH_A if letter == "a" else HASH_B
    return make_catalog(
        path,
        {
            "files": [{"ed2k_hash": ed2k, "size_bytes": 100}],
            "observations": [{"ed2k_hash": ed2k, "filename": "f.avi", "node_id": f"node-{letter}"}],
        },
    )


def test_t1_cli_output_mode_merges(tmp_path: Path) -> None:
    src_a = _seed(tmp_path / "a.db", "a")
    src_b = _seed(tmp_path / "b.db", "b")
    out = tmp_path / "out.db"

    code = main(["--output", str(out), str(src_a), str(src_b)])

    assert code == 0
    assert count(out, "files") == 2


def test_t7_output_exists_without_force_errors(tmp_path: Path) -> None:
    src = _seed(tmp_path / "a.db", "a")
    existing = _seed(tmp_path / "out.db", "b")  # output already exists (1 file: HASH_B).

    code = main(["--output", str(existing), str(src)])

    assert code == 2
    # No overwrite: the existing file is unchanged (still its single file).
    assert count(existing, "files") == 1


def test_t8_output_exists_with_force_appends(tmp_path: Path) -> None:
    src = _seed(tmp_path / "a.db", "a")
    existing = _seed(tmp_path / "out.db", "b")

    code = main(["--output", str(existing), "--force", str(src)])

    assert code == 0
    # Idempotent append: the output now contains the union (HASH_A + HASH_B).
    assert count(existing, "files") == 2

    # Re-merge with --force → no-op (idempotent).
    code = main(["--output", str(existing), "--force", str(src)])
    assert code == 0
    assert count(existing, "files") == 2


def test_t9_into_explicit_dest_is_a_source(tmp_path: Path) -> None:
    src_a = _seed(tmp_path / "a.db", "a")
    src_b = _seed(tmp_path / "b.db", "b")

    code = main(["--into", str(src_a), str(src_a), str(src_b)])

    assert code == 0
    # srcA now contains the union (its own HASH_A + HASH_B from srcB).
    assert count(src_a, "files") == 2

    # Idempotent: re-merging duplicates nothing.
    code = main(["--into", str(src_a), str(src_a), str(src_b)])
    assert code == 0
    assert count(src_a, "files") == 2


def test_t10_into_must_be_a_listed_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src_a = _seed(tmp_path / "a.db", "a")
    src_b = _seed(tmp_path / "b.db", "b")
    other = _seed(tmp_path / "other.db", "a")  # exists but is NOT in the list.

    code = main(["--into", str(other), str(src_a), str(src_b)])

    assert code == 2
    assert f"--into must name a listed source catalog: {other}" in capsys.readouterr().err


def test_t11_output_and_into_mutually_exclusive(tmp_path: Path) -> None:
    src = _seed(tmp_path / "a.db", "a")
    out = tmp_path / "out.db"

    # --output AND --into → argparse error (SystemExit code 2).
    with pytest.raises(SystemExit) as excinfo:
        main(["--output", str(out), "--into", str(src), str(src)])
    assert excinfo.value.code == 2


def test_t11_neither_output_nor_into_required(tmp_path: Path) -> None:
    src = _seed(tmp_path / "a.db", "a")

    # NEITHER --output NOR --into → argparse error (required group → SystemExit code 2).
    with pytest.raises(SystemExit) as excinfo:
        main([str(src)])
    assert excinfo.value.code == 2


def test_t12_force_with_into_is_rejected(tmp_path: Path) -> None:
    src_a = _seed(tmp_path / "a.db", "a")
    src_b = _seed(tmp_path / "b.db", "b")

    code = main(["--into", str(src_a), "--force", str(src_a), str(src_b)])

    assert code == 2


def test_t13_missing_source_file_errors_before_output_created(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = _seed(tmp_path / "a.db", "a")
    missing = tmp_path / "missing.db"
    out = tmp_path / "out.db"

    code = main(["--output", str(out), str(src), str(missing)])

    assert code == 2
    assert f"source catalog not found: {missing}" in capsys.readouterr().err
    # Fail-fast: the output was NOT created (we fail before opening/creating the output).
    assert not out.exists()


def test_cli_logs_the_output_once_done(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    src = _seed(tmp_path / "a.db", "a")
    out = tmp_path / "out.db"
    caplog.set_level("INFO", logger="p2pwatch.merge")

    assert main(["--output", str(out), str(src)]) == 0

    assert f"merge → {out} (1 source catalog(s))" in caplog.messages
    assert caplog.messages[-1] == f"merge done: {out}"


def test_help_says_the_catalog_stays_append_only(capsys: pytest.CaptureFixture[str]) -> None:
    # Every table is append-only again, source points included (source points spec, D1).
    with pytest.raises(SystemExit):
        main(["--help"])

    text = " ".join(capsys.readouterr().out.split())
    assert "append-only preserved" in text
    assert "ranges" not in text


def test_help_calls_the_merged_files_catalogs(capsys: pytest.CaptureFixture[str]) -> None:
    # A bare "source" is a peer sharing a file everywhere else in p2pwatch.
    with pytest.raises(SystemExit):
        main(["--help"])

    text = " ".join(capsys.readouterr().out.split())
    assert "CATALOG [CATALOG ...]" in text
    assert "one of the listed source catalogs" in text

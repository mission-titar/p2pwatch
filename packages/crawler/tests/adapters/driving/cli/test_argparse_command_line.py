"""The command line: one subcommand per driving port, its refusals turned into exit codes."""

import logging
from collections.abc import Sequence
from pathlib import PurePath

import pytest

from p2pwatch.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.ports.driving.catalog_merger import (
    CatalogMerger,
    ListedSourceCatalog,
    MergeError,
    NewCatalog,
)
from p2pwatch.ports.driving.config_validator import ConfigValidator
from p2pwatch.ports.driving.crawler_runner import CrawlerRunner

_DEFAULT_PATHS = (
    PurePath("deploy/crawler.yml"),
    PurePath("deploy/targets.yml"),
    PurePath("deploy/matcher.yml"),
)
_GIVEN_PATHS = (PurePath("c.yml"), PurePath("t.yml"), PurePath("m.yml"))
_GIVEN_ARGV = ["--config", "c.yml", "--targets", "t.yml", "--matcher", "m.yml"]


class _FakeCrawlerRunner(CrawlerRunner):
    """Records the paths of each crawl, and raises ``failure`` when given one."""

    def __init__(self, failure: Exception | None = None) -> None:
        self.crawled_paths: list[tuple[PurePath, PurePath, PurePath]] = []
        self._failure = failure

    async def crawl(
        self, *, config_path: PurePath, targets_path: PurePath, matcher_path: PurePath
    ) -> None:
        self.crawled_paths.append((config_path, targets_path, matcher_path))
        if self._failure is not None:
            raise self._failure


class _FakeConfigValidator(ConfigValidator):
    """Records the paths of each validation, and raises ``refusal`` when given one."""

    def __init__(self, refusal: InvalidConfigError | None = None) -> None:
        self.validated_paths: list[tuple[PurePath, PurePath, PurePath]] = []
        self._refusal = refusal

    def validate_config(
        self, *, config_path: PurePath, targets_path: PurePath, matcher_path: PurePath
    ) -> None:
        self.validated_paths.append((config_path, targets_path, matcher_path))
        if self._refusal is not None:
            raise self._refusal


class _FakeCatalogMerger(CatalogMerger):
    """Records each merge, and raises ``refusal`` when given one."""

    def __init__(self, refusal: MergeError | None = None) -> None:
        self.merges: list[tuple[list[PurePath], NewCatalog | ListedSourceCatalog]] = []
        self._refusal = refusal

    def merge_catalogs(
        self, source_catalogs: Sequence[PurePath], destination: NewCatalog | ListedSourceCatalog
    ) -> None:
        self.merges.append((list(source_catalogs), destination))
        if self._refusal is not None:
            raise self._refusal


def _command_line(
    crawler_runner: CrawlerRunner | None = None,
    config_validator: ConfigValidator | None = None,
    catalog_merger: CatalogMerger | None = None,
) -> ArgparseCommandLine:
    return ArgparseCommandLine(
        crawler_runner=crawler_runner or _FakeCrawlerRunner(),
        config_validator=config_validator or _FakeConfigValidator(),
        catalog_merger=catalog_merger or _FakeCatalogMerger(),
    )


def test_crawl_runs_the_crawler_on_the_paths_given() -> None:
    crawler_runner = _FakeCrawlerRunner()

    assert _command_line(crawler_runner=crawler_runner).run(["crawl", *_GIVEN_ARGV]) == 0

    assert crawler_runner.crawled_paths == [_GIVEN_PATHS]


def test_crawl_defaults_to_the_deploy_directory() -> None:
    crawler_runner = _FakeCrawlerRunner()

    assert _command_line(crawler_runner=crawler_runner).run(["crawl"]) == 0

    assert crawler_runner.crawled_paths == [_DEFAULT_PATHS]


def test_crawl_refuses_to_start_on_an_invalid_config(capsys: pytest.CaptureFixture[str]) -> None:
    crawler_runner = _FakeCrawlerRunner(InvalidConfigError("search: section missing"))

    assert _command_line(crawler_runner=crawler_runner).run(["crawl"]) == 1

    assert capsys.readouterr().err == "Invalid config, refusing to start: search: section missing\n"


def test_crawl_exits_zero_when_the_shutdown_deadline_fires(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The bound firing is the crawler keeping its promise not to hang, not a crash.
    crawler_runner = _FakeCrawlerRunner(TimeoutError())

    assert _command_line(crawler_runner=crawler_runner).run(["crawl"]) == 0

    assert "Shutdown deadline elapsed" in capsys.readouterr().err


def test_validate_config_validates_the_paths_given_and_starts_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    crawler_runner = _FakeCrawlerRunner()
    config_validator = _FakeConfigValidator()
    command_line = _command_line(crawler_runner, config_validator)

    assert command_line.run(["validate-config", *_GIVEN_ARGV]) == 0

    assert config_validator.validated_paths == [_GIVEN_PATHS]
    assert crawler_runner.crawled_paths == []
    assert capsys.readouterr().out == "Config valid\n"


def test_validate_config_defaults_to_the_deploy_directory() -> None:
    config_validator = _FakeConfigValidator()

    assert _command_line(config_validator=config_validator).run(["validate-config"]) == 0

    assert config_validator.validated_paths == [_DEFAULT_PATHS]


def test_validate_config_reports_an_invalid_config(capsys: pytest.CaptureFixture[str]) -> None:
    config_validator = _FakeConfigValidator(InvalidConfigError("'episodes' section: list expected"))

    assert _command_line(config_validator=config_validator).run(["validate-config"]) == 1

    assert capsys.readouterr().err == "Invalid config: 'episodes' section: list expected\n"


def test_the_bare_invocation_is_refused_with_a_usage_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # 4.x ran the crawler without a subcommand; v5 names it.
    crawler_runner = _FakeCrawlerRunner()

    with pytest.raises(SystemExit) as exit_info:
        _command_line(crawler_runner=crawler_runner).run(["--config", "deploy/crawler.yml"])

    assert exit_info.value.code == 2
    assert capsys.readouterr().err.startswith("usage: p2pwatch ")
    assert crawler_runner.crawled_paths == []


def test_the_help_lists_the_subcommands_and_names_no_observer_mode(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        _command_line().run(["--help"])

    help_text = capsys.readouterr().out
    assert exit_info.value.code == 0
    assert "{crawl,validate-config,merge}" in help_text
    assert "observer" not in help_text  # the config says ``download.enabled``


@pytest.mark.parametrize(
    "argv", [["crawl"], ["validate-config"], ["merge", "--output", "out.db", "a.db"]]
)
def test_every_subcommand_logs_at_info_with_its_logger_name(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    root = logging.getLogger()
    root_level = root.level
    request.addfinalizer(lambda: root.setLevel(root_level))
    monkeypatch.setattr(root, "handlers", [])  # pytest's own, which basicConfig would keep

    _command_line().run(argv)

    [handler] = root.handlers
    assert handler.formatter is not None
    assert handler.formatter._fmt == "%(asctime)s %(levelname)s %(name)s %(message)s"
    assert root.level == logging.INFO


_A = PurePath("a.db")
_B = PurePath("b.db")


@pytest.mark.parametrize(
    ("options", "destination"),
    [
        (["--output", "out.db"], NewCatalog(PurePath("out.db"), force=False)),
        (["-o", "out.db", "--force"], NewCatalog(PurePath("out.db"), force=True)),
        (["--into", "a.db"], ListedSourceCatalog(_A)),
    ],
)
def test_merge_merges_the_catalogs_given_into_the_destination_given(
    options: list[str], destination: NewCatalog | ListedSourceCatalog
) -> None:
    catalog_merger = _FakeCatalogMerger()

    assert (
        _command_line(catalog_merger=catalog_merger).run(["merge", *options, "a.db", "b.db"]) == 0
    )

    assert catalog_merger.merges == [([_A, _B], destination)]


def test_merge_refuses_force_with_into(capsys: pytest.CaptureFixture[str]) -> None:
    catalog_merger = _FakeCatalogMerger()

    argv = ["merge", "--into", "a.db", "--force", "a.db", "b.db"]
    assert _command_line(catalog_merger=catalog_merger).run(argv) == 2

    assert capsys.readouterr().err == "Merge failed: --force makes no sense with --into\n"
    assert catalog_merger.merges == []


@pytest.mark.parametrize(
    "options", [["--output", "out.db", "--into", "a.db"], []], ids=["both", "neither"]
)
def test_merge_takes_exactly_one_destination(options: list[str]) -> None:
    catalog_merger = _FakeCatalogMerger()

    with pytest.raises(SystemExit) as exit_info:
        _command_line(catalog_merger=catalog_merger).run(["merge", *options, "a.db"])

    assert exit_info.value.code == 2
    assert catalog_merger.merges == []


def test_merge_reports_a_refused_merge(capsys: pytest.CaptureFixture[str]) -> None:
    catalog_merger = _FakeCatalogMerger(MergeError("source catalog not found: b.db"))

    argv = ["merge", "--output", "out.db", "a.db", "b.db"]
    assert _command_line(catalog_merger=catalog_merger).run(argv) == 2

    assert capsys.readouterr().err == "Merge failed: source catalog not found: b.db\n"


def test_merge_help_names_the_catalogs_and_keeps_them_append_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # A bare "source" is a peer sharing a file everywhere else in p2pwatch.
    with pytest.raises(SystemExit):
        _command_line().run(["merge", "--help"])

    help_text = " ".join(capsys.readouterr().out.split())
    assert "CATALOG [CATALOG ...]" in help_text
    assert "one of the listed source catalogs" in help_text
    assert "append-only preserved" in help_text

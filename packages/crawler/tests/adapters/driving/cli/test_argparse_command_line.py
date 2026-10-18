"""The command line: one subcommand per driving port, its refusals turned into exit codes."""

import logging
from pathlib import PurePath

import pytest

from p2pwatch.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from p2pwatch.domain.invalid_config import InvalidConfigError
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


def _command_line(
    crawler_runner: CrawlerRunner | None = None, config_validator: ConfigValidator | None = None
) -> ArgparseCommandLine:
    return ArgparseCommandLine(
        crawler_runner=crawler_runner or _FakeCrawlerRunner(),
        config_validator=config_validator or _FakeConfigValidator(),
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
    assert "{crawl,validate-config}" in help_text
    assert "observer" not in help_text  # the config says ``download.enabled``


@pytest.mark.parametrize("subcommand", ["crawl", "validate-config"])
def test_every_subcommand_logs_at_info_with_its_logger_name(
    subcommand: str, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    root = logging.getLogger()
    root_level = root.level
    request.addfinalizer(lambda: root.setLevel(root_level))
    monkeypatch.setattr(root, "handlers", [])  # pytest's own, which basicConfig would keep

    _command_line().run([subcommand])

    [handler] = root.handlers
    assert handler.formatter is not None
    assert handler.formatter._fmt == "%(asctime)s %(levelname)s %(name)s %(message)s"
    assert root.level == logging.INFO

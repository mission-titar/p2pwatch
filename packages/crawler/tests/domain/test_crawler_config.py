from datetime import timedelta
from pathlib import PurePath

from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.crawler_config import (
    BackoffConfig,
    CrawlerConfig,
    DownloadConfig,
    ObservabilityConfig,
    SearchConfig,
    WebuiConfig,
    cross_value_problems,
)

_FILE = PurePath("/srv/crawler.yml")


def _default_webui() -> WebuiConfig:
    """The webui of a section that sets nothing: the default aMule link and gap."""
    return WebuiConfig(
        amule_url="http://localhost:4711",
        source_period_gap=timedelta(seconds=990),
    )


def _with_backoff(*, base_seconds: float, cap_seconds: float) -> CrawlerConfig:
    backoff = BackoffConfig(
        base_seconds=base_seconds, cap_seconds=cap_seconds, factor=2.0, jitter_ratio=0.3
    )
    return CrawlerConfig(
        search=SearchConfig(keywords=("keroro",), backoff=backoff),
        shutdown_deadline_seconds=10.0,
        amule_api_password="secret",
        catalog_db_path="/data/catalog.db",
        local_db_path="/data/local.db",
        observability=ObservabilityConfig(
            log_level="INFO", notification_timeout_seconds=5.0, notifications=()
        ),
        download=None,
        webui=_default_webui(),
    )


def test_a_backoff_cap_at_its_base_is_no_problem() -> None:
    config = _with_backoff(base_seconds=10.0, cap_seconds=10.0)
    assert cross_value_problems(config, file_path=_FILE) == ()


def test_a_backoff_cap_below_its_base_is_a_problem() -> None:
    config = _with_backoff(base_seconds=10.0, cap_seconds=9.5)
    assert cross_value_problems(config, file_path=_FILE) == (
        ConfigProblem(
            file_path=_FILE,
            key="search.backoff.cap_seconds",
            message="should be at least base_seconds",
        ),
    )


def test_the_sources_are_read_a_poll_after_their_interval() -> None:
    # The step runs on the first round past its interval (source points spec, D3).
    config = DownloadConfig(
        poll_interval_seconds=30.0,
        min_free_bytes=1,
        lost_after=timedelta(hours=1),
        output_directory="/data/out",
        reappeared_after=timedelta(hours=1),
        sources_interval=timedelta(seconds=120),
    )
    assert config.time_between_source_reads == timedelta(seconds=150)

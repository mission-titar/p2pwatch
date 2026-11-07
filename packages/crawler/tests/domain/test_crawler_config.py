import re
from datetime import timedelta
from pathlib import PurePath
from typing import Any

import pytest

from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.config_value_error import ConfigValueError
from p2pwatch.domain.crawler_config import (
    BackoffConfig,
    CrawlerConfig,
    DownloadConfig,
    ObservabilityConfig,
    SearchConfig,
    WebuiConfig,
    cross_value_problems,
    parse_download,
)

_FILE = PurePath("/srv/crawler.yml")


def _minimal_raw() -> dict[str, Any]:
    """Valid policy + minimal wiring (password without ${}, base paths), observer mode."""
    return {
        "search": {
            "keywords": ["keroro", "titar"],
            "backoff": {
                "base_seconds": 2.0,
                "cap_seconds": 300.0,
                "factor": 2.0,
                "jitter_ratio": 0.3,
            },
        },
        "shutdown_deadline_seconds": 10.0,
        "amule_api_password": "secret",
        "catalog_db_path": "/data/catalog.db",
        "local_db_path": "/data/local.db",
    }


def _full_download_section() -> dict[str, Any]:
    return {
        "enabled": True,
        "poll_interval_seconds": 30.0,
        "min_free_bytes": 1_000_000_000,
        "lost_after_seconds": 3600.0,
        "output_dir": "/data/out",
        "reappeared_after_seconds": 5400.0,
        "sources_interval_seconds": 120.0,
    }


def _default_webui() -> WebuiConfig:
    """The webui of a section that sets nothing: the default aMule link and gap."""
    return WebuiConfig(
        amule_url="http://localhost:4711",
        source_period_gap=timedelta(seconds=990),
    )


def _section(raw: dict[str, Any], *, path: str) -> dict[str, Any]:
    """The mapping at the dotted ``path`` of ``raw``."""
    for name in path.split("."):
        raw = raw[name]
    return raw


def _printed_path(section: str, *, key: str) -> str:
    return re.escape(f"{section}.{key}")


def _parse_sections(raw: dict[str, Any]) -> None:
    """Each section of ``raw`` through its parse, as the config adapter hands it."""
    parse_download(raw["download"])


# --------------------------------------------------------------------- policy


@pytest.mark.parametrize("value", ["souvent", True], ids=["text", "bool"])
def test_a_number_of_a_section_is_a_number(value: object) -> None:
    with pytest.raises(ConfigValueError, match="download.poll_interval_seconds: number"):
        parse_download(_full_download_section() | {"poll_interval_seconds": value})


@pytest.mark.parametrize("number", [float("inf"), float("nan")], ids=["inf", "nan"])
@pytest.mark.parametrize(
    ("section", "key"),
    [
        ("download", "poll_interval_seconds"),
        ("download", "lost_after_seconds"),
        ("download", "reappeared_after_seconds"),
        ("download", "sources_interval_seconds"),
    ],
)
def test_a_number_that_is_not_finite_is_refused_by_name(
    *, section: str, key: str, number: float
) -> None:
    # .inf would make a sleep endless and .nan passes every comparison.
    raw = _minimal_raw() | {"download": _full_download_section(), "observability": {}}
    _section(raw, path=section)[key] = number
    with pytest.raises(
        ConfigValueError, match=rf"^{_printed_path(section, key=key)}: finite number expected"
    ):
        _parse_sections(raw)


def _with_seconds(section: str, *, key: str, seconds: int) -> dict[str, Any]:
    """A full config whose ``key`` holds ``seconds``, the backoff's cap above any floor."""
    raw = _minimal_raw() | {"download": _full_download_section(), "observability": {}, "webui": {}}
    _section(raw, path=section)[key] = seconds
    return raw


@pytest.mark.parametrize(
    ("section", "key"),
    [
        ("download", "poll_interval_seconds"),
        ("download", "sources_interval_seconds"),
    ],
)
def test_a_duration_is_at_most_a_day(*, section: str, key: str) -> None:
    _parse_sections(_with_seconds(section, key=key, seconds=86_400))
    with pytest.raises(
        ConfigValueError,
        match=rf"^{_printed_path(section, key=key)}: at most 86400 seconds expected, got 86401",
    ):
        _parse_sections(_with_seconds(section, key=key, seconds=86_401))


@pytest.mark.parametrize("key", ["lost_after_seconds", "reappeared_after_seconds"])
def test_an_absence_is_at_most_thirty_days(key: str) -> None:
    _parse_sections(_with_seconds("download", key=key, seconds=2_592_000))
    with pytest.raises(
        ConfigValueError, match=rf"download\.{key}: at most 2592000 seconds expected, got 2592001"
    ):
        _parse_sections(_with_seconds("download", key=key, seconds=2_592_001))


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


# ----------------------------------------------------------------- download


def test_download_absent_is_observer() -> None:
    assert parse_download({}) is None


def test_download_enabled_false_is_observer_without_requiring_wiring() -> None:
    # enabled:false ⇒ we do NOT read the rest: a missing poll_interval is NOT an error.
    assert parse_download({"enabled": False}) is None


def test_download_section_without_enabled_defaults_to_observer() -> None:
    # enabled missing → default false → download None (missing-key branch of _bool_default).
    assert parse_download({"poll_interval_seconds": 30.0}) is None


def test_download_enabled_non_bool_is_fatal() -> None:
    with pytest.raises(ConfigValueError, match="boolean expected"):
        parse_download({"enabled": "oui"})


def test_download_enabled_true_requires_the_poll_interval() -> None:
    with pytest.raises(ConfigValueError, match="poll_interval_seconds"):
        parse_download({"enabled": True, "min_free_bytes": 1024})


def test_download_enabled_true_full_is_download_mode() -> None:
    config = parse_download(_full_download_section())
    assert config == DownloadConfig(
        poll_interval_seconds=30.0,
        min_free_bytes=1_000_000_000,
        lost_after=timedelta(hours=1),
        output_directory="/data/out",
        reappeared_after=timedelta(seconds=5400),
        sources_interval=timedelta(seconds=120),
    )


def test_the_sources_are_read_a_poll_after_their_interval() -> None:
    # The step runs on the first round past its interval (source points spec, D3).
    config = parse_download(_full_download_section())
    assert config is not None
    assert config.time_between_source_reads == timedelta(seconds=150)


def test_download_sources_interval_defaults_to_five_minutes() -> None:
    section = _full_download_section()
    del section["sources_interval_seconds"]
    config = parse_download(section)
    assert config is not None
    assert config.sources_interval == timedelta(seconds=300)


@pytest.mark.parametrize("seconds", [0, -1, float("inf"), float("nan")])
def test_download_sources_interval_is_a_positive_finite_number(seconds: float) -> None:
    section = _full_download_section() | {"sources_interval_seconds": seconds}
    with pytest.raises(ConfigValueError, match=r"download\.sources_interval_seconds"):
        parse_download(section)


def test_download_poll_interval_must_be_positive() -> None:
    section = _full_download_section() | {"poll_interval_seconds": 0.0}
    with pytest.raises(ConfigValueError, match="strictly positive"):
        parse_download(section)


def test_download_min_free_must_be_positive_integer() -> None:
    section = _full_download_section() | {"min_free_bytes": 0}
    with pytest.raises(ConfigValueError, match="strictly positive"):
        parse_download(section)


def test_download_lost_after_must_be_positive() -> None:
    section = _full_download_section() | {"lost_after_seconds": 0.0}
    with pytest.raises(ConfigValueError, match="strictly positive"):
        parse_download(section)


def test_download_space_and_ttl_knobs_have_defaults() -> None:
    # All three are new in 2026-09-13: an operator config predating them must still boot, so
    # they default instead of failing fast like the older required keys.
    section = _full_download_section()
    for key in ("min_free_bytes", "lost_after_seconds", "output_dir"):
        del section[key]
    config = parse_download(section)
    assert config is not None
    assert config.min_free_bytes == 10_737_418_240  # 10 GiB
    assert config.lost_after == timedelta(hours=24)
    assert config.output_directory == "/downloads"  # what deploy/compose.yml mounts


def test_a_source_reappears_after_12_hours_by_default() -> None:
    section = _full_download_section()
    del section["reappeared_after_seconds"]
    config = parse_download(section)
    assert config is not None
    assert config.reappeared_after == timedelta(hours=12)


@pytest.mark.parametrize("seconds", [0, -1, float("inf"), float("nan"), 1e15])
def test_reappeared_after_seconds_is_a_positive_finite_duration(seconds: float) -> None:
    # .inf overflows a duration and .nan would silently disable the event (D9).
    section = _full_download_section() | {"reappeared_after_seconds": seconds}
    with pytest.raises(ConfigValueError, match=r"download\.reappeared_after_seconds"):
        parse_download(section)


def test_download_output_dir_must_be_a_string() -> None:
    section = _full_download_section() | {"output_dir": 42}
    with pytest.raises(ConfigValueError, match="output_dir"):
        parse_download(section)

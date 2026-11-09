from datetime import timedelta
from pathlib import PurePath
from typing import Any

import pytest

from p2pwatch.adapters.driven.config.crawler_config_schema import crawler_config_from_document
from p2pwatch.domain.crawler_config import (
    BackoffConfig,
    CrawlerConfig,
    DownloadConfig,
    NotificationTarget,
    ObservabilityConfig,
    SearchConfig,
    WebuiConfig,
)
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.observability.policy import Audience

_FILE = PurePath("/srv/crawler.yml")


def _document() -> dict[str, Any]:
    """Every root key and section of ``crawler.yml``, their values valid."""
    return {
        "search": {
            "keywords": ["keroro"],
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
        "observability": {},
        "download": {"enabled": False},
        "webui": {},
    }


def _problems(document: dict[str, Any]) -> list[tuple[str | None, str]]:
    """The key and message of each problem of ``document``, all of them in ``_FILE``."""
    with pytest.raises(InvalidConfigError) as raised:
        crawler_config_from_document(document, file_path=_FILE)
    assert {problem.file_path for problem in raised.value.problems} == {_FILE}
    return [(problem.key, problem.message) for problem in raised.value.problems]


def test_a_valid_document_builds_its_crawler_config() -> None:
    assert crawler_config_from_document(_document(), file_path=_FILE) == CrawlerConfig(
        search=SearchConfig(
            keywords=("keroro",),
            backoff=BackoffConfig(
                base_seconds=2.0, cap_seconds=300.0, factor=2.0, jitter_ratio=0.3
            ),
        ),
        shutdown_deadline_seconds=10.0,
        amule_api_password="secret",
        catalog_db_path="/data/catalog.db",
        local_db_path="/data/local.db",
        observability=ObservabilityConfig(
            log_level="INFO", notification_timeout_seconds=5.0, notifications=()
        ),
        download=None,
        webui=WebuiConfig(
            amule_url="http://localhost:4711", source_period_gap=timedelta(seconds=990)
        ),
    )


@pytest.mark.parametrize("section", ["observability", "download", "webui"])
def test_an_absent_section_takes_its_defaults(section: str) -> None:
    document = _document()
    del document[section]
    config = crawler_config_from_document(document, file_path=_FILE)
    assert config == crawler_config_from_document(_document(), file_path=_FILE)


@pytest.mark.parametrize(
    "key",
    [
        "shutdown_deadline_seconds",
        "amule_api_password",
        "catalog_db_path",
        "local_db_path",
        "search",
    ],
)
def test_a_root_key_absent_is_required(key: str) -> None:
    document = _document()
    del document[key]
    assert _problems(document) == [(key, "Field required")]


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("shutdown_deadline_seconds", "souvent", "Input should be a valid number"),
        ("shutdown_deadline_seconds", True, "Input should be a valid number"),
        ("shutdown_deadline_seconds", float("inf"), "Input should be a finite number"),
        ("shutdown_deadline_seconds", float("nan"), "Input should be a finite number"),
        ("shutdown_deadline_seconds", 0, "Input should be greater than 0"),
        ("shutdown_deadline_seconds", 86_401, "Input should be less than or equal to 86400"),
        ("amule_api_password", "", "String should have at least 1 character"),
        ("amule_api_password", 1234, "Input should be a valid string"),
        ("catalog_db_path", "", "String should have at least 1 character"),
        ("local_db_path", None, "Input should be a valid string"),
    ],
)
def test_a_root_value_out_of_its_type_is_refused(*, key: str, value: object, message: str) -> None:
    assert _problems(_document() | {key: value}) == [(key, message)]


def test_a_deadline_of_a_day_is_accepted() -> None:
    document = _document() | {"shutdown_deadline_seconds": 86_400}
    config = crawler_config_from_document(document, file_path=_FILE)
    assert config.shutdown_deadline_seconds == 86_400


def _with(path: str, *, value: object) -> dict[str, Any]:
    """``_document()`` holding ``value`` at the dotted ``path``."""
    document = _document()
    *sections, key = path.split(".")
    mapping = document
    for section in sections:
        mapping = mapping[section]
    mapping[key] = value
    return document


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        ("keywords", [], "List should have at least 1 item after validation, not 0"),
        ("keywords", "keroro", "Input should be a valid list"),
        ("backoff", [1, 2], "Input should be a valid dictionary"),
        ("backoff.base_seconds", float("inf"), "Input should be a finite number"),
        ("backoff.cap_seconds", float("nan"), "Input should be a finite number"),
        ("backoff.factor", float("inf"), "Input should be a finite number"),
        ("backoff.jitter_ratio", float("nan"), "Input should be a finite number"),
        ("backoff.base_seconds", 86_401, "Input should be less than or equal to 86400"),
        ("backoff.cap_seconds", 0, "Input should be greater than 0"),
        ("backoff.factor", 0.5, "Input should be greater than or equal to 1"),
        ("backoff.factor", 11, "Input should be less than or equal to 10"),
        ("backoff.factor", "2", "Input should be a valid number"),
        ("backoff.jitter_ratio", -0.1, "Input should be greater than or equal to 0"),
        ("backoff.jitter_ratio", 1.5, "Input should be less than or equal to 1"),
        ("unread", 1, "Extra inputs are not permitted"),
        ("backoff.unread", 1, "Extra inputs are not permitted"),
    ],
)
def test_a_search_value_out_of_its_type_is_refused(
    *, path: str, value: object, message: str
) -> None:
    assert _problems(_with(f"search.{path}", value=value)) == [(f"search.{path}", message)]


@pytest.mark.parametrize(
    ("keywords", "key", "message"),
    [
        (["keroro", 42], "search.keywords[1]", "Input should be a valid string"),
        ([""], "search.keywords[0]", "String should have at least 1 character"),
    ],
)
def test_a_keyword_is_a_non_empty_string(*, keywords: list[object], key: str, message: str) -> None:
    assert _problems(_with("search.keywords", value=keywords)) == [(key, message)]


@pytest.mark.parametrize("key", ["keywords", "backoff", "backoff.factor"])
def test_a_search_key_absent_is_required(key: str) -> None:
    document = _document()
    *sections, name = key.split(".")
    mapping = document["search"]
    for section in sections:
        mapping = mapping[section]
    del mapping[name]
    assert _problems(document) == [(f"search.{key}", "Field required")]


def test_a_backoff_of_a_day_without_jitter_is_accepted() -> None:
    backoff = {"base_seconds": 86_400, "cap_seconds": 86_400, "factor": 1, "jitter_ratio": 0}
    config = crawler_config_from_document(_with("search.backoff", value=backoff), file_path=_FILE)
    assert config.search.backoff == BackoffConfig(
        base_seconds=86_400, cap_seconds=86_400, factor=1, jitter_ratio=0
    )


def test_a_backoff_at_its_upper_bounds_is_accepted() -> None:
    backoff = {"base_seconds": 2, "cap_seconds": 86_400, "factor": 10, "jitter_ratio": 1}
    config = crawler_config_from_document(_with("search.backoff", value=backoff), file_path=_FILE)
    assert config.search.backoff == BackoffConfig(
        base_seconds=2, cap_seconds=86_400, factor=10, jitter_ratio=1
    )


def test_a_backoff_cap_below_its_base_is_refused() -> None:
    document = _with("search.backoff.cap_seconds", value=1.0)
    assert _problems(document) == [
        ("search.backoff.cap_seconds", "should be at least base_seconds")
    ]


def test_the_rules_across_values_wait_for_the_file_to_hold() -> None:
    document = _with("search.backoff.cap_seconds", value=1.0) | {"shutdown_deadline_seconds": 0}
    assert _problems(document) == [("shutdown_deadline_seconds", "Input should be greater than 0")]


def test_the_webui_values_build_its_config() -> None:
    webui = {"amule_url": "https://mule.example.org/amule", "source_period_gap_seconds": 86_400}
    config = crawler_config_from_document(_document() | {"webui": webui}, file_path=_FILE)
    assert config.webui == WebuiConfig(
        amule_url="https://mule.example.org/amule", source_period_gap=timedelta(days=1)
    )


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("amule_url", "", "String should have at least 1 character"),
        ("amule_url", 4711, "Input should be a valid string"),
        ("source_period_gap_seconds", 0, "Input should be greater than 0"),
        ("source_period_gap_seconds", 86_401, "Input should be less than or equal to 86400"),
        ("source_period_gap_seconds", float("inf"), "Input should be a finite number"),
        ("source_period_gap_seconds", float("nan"), "Input should be a finite number"),
        ("source_period_gap_seconds", "600", "Input should be a valid number"),
        ("unread", 1, "Extra inputs are not permitted"),
        ("enabled", True, "was removed, delete it from crawler.yml"),
        ("host", "0.0.0.0", "was removed, delete it from crawler.yml"),
        ("port", 8080, "was removed, delete it from crawler.yml"),
    ],
)
def test_a_webui_value_out_of_its_type_is_refused(*, key: str, value: object, message: str) -> None:
    assert _problems(_with(f"webui.{key}", value=value)) == [(f"webui.{key}", message)]


def test_the_observability_values_build_its_config() -> None:
    observability = {
        "log_level": "DEBUG",
        "notification_timeout_seconds": 86_400,
        "notifications": [
            {"url": "discord://a", "audience": "community", "node_prefix": False},
            {"url": "discord://b", "audience": "operations"},
        ],
    }
    document = _document() | {"observability": observability}
    assert crawler_config_from_document(document, file_path=_FILE).observability == (
        ObservabilityConfig(
            log_level="DEBUG",
            notification_timeout_seconds=86_400,
            notifications=(
                NotificationTarget(
                    url="discord://a", audience=Audience.COMMUNITY, node_prefix=False
                ),
                NotificationTarget(
                    url="discord://b", audience=Audience.OPERATIONS, node_prefix=True
                ),
            ),
        )
    )


_LOG_LEVELS = "'DEBUG', 'INFO', 'WARNING', 'ERROR' or 'CRITICAL'"


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("log_level", "LOUD", f"Input should be {_LOG_LEVELS}"),
        ("log_level", 10, f"Input should be {_LOG_LEVELS}"),
        ("notification_timeout_seconds", 0, "Input should be greater than 0"),
        ("notification_timeout_seconds", 86_401, "Input should be less than or equal to 86400"),
        ("notification_timeout_seconds", float("inf"), "Input should be a finite number"),
        ("notification_timeout_seconds", float("nan"), "Input should be a finite number"),
        ("notification_timeout_seconds", True, "Input should be a valid number"),
        ("notifications", "discord://a", "Input should be a valid list"),
        ("unread", 1, "Extra inputs are not permitted"),
        ("metrics", {"enabled": True}, "was removed, delete it from crawler.yml"),
    ],
)
def test_an_observability_value_out_of_its_type_is_refused(
    *, key: str, value: object, message: str
) -> None:
    document = _with(f"observability.{key}", value=value)
    assert _problems(document) == [(f"observability.{key}", message)]


def _with_notification(notification: object) -> dict[str, Any]:
    return _with("observability.notifications", value=[notification])


@pytest.mark.parametrize(
    ("notification", "key", "message"),
    [
        ("discord://a", "", "Input should be a valid dictionary"),
        ({"url": "", "audience": "community"}, ".url", "String should have at least 1 character"),
        ({"url": 42, "audience": "community"}, ".url", "Input should be a valid string"),
        ({"audience": "community"}, ".url", "Field required"),
        (
            {"url": "x", "audience": "nope"},
            ".audience",
            "Input should be 'community' or 'operations'",
        ),
        ({"url": "x"}, ".audience", "Field required"),
        (
            {"url": "x", "audience": "community", "node_prefix": "no"},
            ".node_prefix",
            "Input should be a valid boolean",
        ),
        (
            {"url": "x", "audience": "community", "unread": 1},
            ".unread",
            "Extra inputs are not permitted",
        ),
    ],
)
def test_a_notification_value_out_of_its_type_is_refused(
    *, notification: object, key: str, message: str
) -> None:
    problems = _problems(_with_notification(notification))
    assert problems == [(f"observability.notifications[0]{key}", message)]


@pytest.mark.parametrize(
    "notification",
    [{"url": "x", "tag": "community"}, {"url": "x", "tag": "community", "audience": "community"}],
)
def test_a_notification_tag_is_one_problem_naming_its_new_name(notification: object) -> None:
    assert _problems(_with_notification(notification)) == [
        ("observability.notifications[0].tag", "was renamed 'audience', rename it in crawler.yml")
    ]


def _download(**keys: object) -> dict[str, Any]:
    """``_document()`` with downloads on, every download key set, then ``keys``."""
    download = {
        "enabled": True,
        "poll_interval_seconds": 30.0,
        "min_free_bytes": 1_000_000_000,
        "lost_after_seconds": 3600.0,
        "output_dir": "/data/out",
        "reappeared_after_seconds": 5400.0,
        "sources_interval_seconds": 120.0,
    }
    return _document() | {"download": download | keys}


def test_the_download_values_build_its_config() -> None:
    assert crawler_config_from_document(_download(), file_path=_FILE).download == DownloadConfig(
        poll_interval_seconds=30.0,
        min_free_bytes=1_000_000_000,
        lost_after=timedelta(hours=1),
        output_directory="/data/out",
        reappeared_after=timedelta(seconds=5400),
        sources_interval=timedelta(seconds=120),
    )


def test_a_download_on_takes_the_defaults_of_its_keys_but_the_poll_interval() -> None:
    document = _document() | {"download": {"enabled": True, "poll_interval_seconds": 30}}
    assert crawler_config_from_document(document, file_path=_FILE).download == DownloadConfig(
        poll_interval_seconds=30.0,
        min_free_bytes=10_737_418_240,
        lost_after=timedelta(hours=24),
        output_directory="/downloads",
        reappeared_after=timedelta(hours=12),
        sources_interval=timedelta(minutes=5),
    )


@pytest.mark.parametrize(
    "download",
    [{}, {"enabled": False}, {"poll_interval_seconds": 30.0}, {"min_free_bytes": 1024}],
    ids=["empty", "off", "poll-without-enabled", "wiring-without-enabled"],
)
def test_a_download_not_enabled_is_off_its_wiring_not_required(download: dict[str, Any]) -> None:
    document = _document() | {"download": download}
    assert crawler_config_from_document(document, file_path=_FILE).download is None


def test_a_download_on_requires_its_poll_interval() -> None:
    document = _document() | {"download": {"enabled": True, "min_free_bytes": 1024}}
    assert _problems(document) == [("download.poll_interval_seconds", "Field required")]


@pytest.mark.parametrize(
    ("key", "seconds"),
    [
        ("poll_interval_seconds", 86_400),
        ("sources_interval_seconds", 86_400),
        ("lost_after_seconds", 2_592_000),
        ("reappeared_after_seconds", 2_592_000),
    ],
)
def test_a_download_duration_is_accepted_up_to_its_bound(*, key: str, seconds: int) -> None:
    crawler_config_from_document(_download(**{key: seconds}), file_path=_FILE)


@pytest.mark.parametrize("enabled", ["oui", 1, None])
def test_a_download_enabled_is_a_boolean(enabled: object) -> None:
    assert _problems(_download(enabled=enabled)) == [
        ("download.enabled", "Input should be a valid boolean")
    ]


_A_DAY = "Input should be less than or equal to 86400"
_THIRTY_DAYS = "Input should be less than or equal to 2592000"


@pytest.mark.parametrize("enabled", [True, False], ids=["on", "off"])
@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("poll_interval_seconds", "souvent", "Input should be a valid number"),
        ("poll_interval_seconds", True, "Input should be a valid number"),
        ("poll_interval_seconds", 0.0, "Input should be greater than 0"),
        ("poll_interval_seconds", 86_401, _A_DAY),
        ("poll_interval_seconds", None, "Input should be a valid number"),
        ("min_free_bytes", 0, "Input should be greater than 0"),
        ("min_free_bytes", 1024.0, "Input should be a valid integer"),
        ("min_free_bytes", True, "Input should be a valid integer"),
        ("lost_after_seconds", 0.0, "Input should be greater than 0"),
        ("lost_after_seconds", 2_592_001, _THIRTY_DAYS),
        ("output_dir", 42, "Input should be a valid string"),
        ("output_dir", "", "String should have at least 1 character"),
        ("reappeared_after_seconds", -1, "Input should be greater than 0"),
        ("reappeared_after_seconds", 1e15, _THIRTY_DAYS),
        ("sources_interval_seconds", 0, "Input should be greater than 0"),
        ("sources_interval_seconds", 86_401, _A_DAY),
        ("unread", 1, "Extra inputs are not permitted"),
    ]
    + [
        (key, number, "Input should be a finite number")
        for key in (
            "poll_interval_seconds",
            "lost_after_seconds",
            "reappeared_after_seconds",
            "sources_interval_seconds",
        )
        for number in (float("inf"), float("nan"))
    ],
)
def test_a_download_value_out_of_its_type_is_refused_whether_on_or_off(
    *, key: str, value: object, message: str, enabled: bool
) -> None:
    document = _download(enabled=enabled)
    document["download"][key] = value
    assert _problems(document) == [(f"download.{key}", message)]


def test_a_root_key_nothing_reads_is_refused() -> None:
    document = _document() | {"amules": [{"name": "amule-1", "password": "x"}]}
    assert _problems(document) == [("amules", "Extra inputs are not permitted")]


@pytest.mark.parametrize(
    "key",
    [
        "cycle_interval_seconds",
        "decision_poll_interval_seconds",
        "keyword_pause_max_seconds",
        "keyword_pause_min_seconds",
        "node_id",
        "port_sync",
        "search_poll_budget_seconds",
        "search_poll_interval_seconds",
    ],
)
def test_a_removed_root_key_is_refused_by_name(key: str) -> None:
    assert _problems(_document() | {key: None}) == [
        (key, "was removed, delete it from crawler.yml")
    ]


def test_the_root_backoff_is_one_problem_naming_its_new_place() -> None:
    document = _document() | {"backoff": _document()["search"].pop("backoff")}
    del document["search"]["backoff"]
    assert _problems(document) == [("backoff", "moved to 'search.backoff', move it in crawler.yml")]


@pytest.mark.parametrize("section", ["search", "observability", "download", "webui"])
def test_a_section_that_is_no_mapping_is_refused(section: str) -> None:
    assert _problems(_document() | {section: [1, 2]}) == [
        (section, "Input should be a valid dictionary")
    ]


def test_every_problem_of_the_root_and_of_each_section_is_listed() -> None:
    document = _document() | {
        "shutdown_deadline_seconds": "souvent",
        "port_sync": {"enabled": True},
        "amules": [],
        "observability": {"log_level": "LOUD"},
        "download": {"enabled": "oui"},
        "webui": {"amule_url": ""},
    }
    assert [key for key, _ in _problems(document)] == [
        "shutdown_deadline_seconds",
        "download.enabled",
        "observability.log_level",
        "webui.amule_url",
        "port_sync",
        "amules",
    ]


def test_the_error_chains_no_pydantic_error_which_holds_the_values() -> None:
    with pytest.raises(InvalidConfigError) as raised:
        crawler_config_from_document(_document() | {"unread": "s3cr3t"}, file_path=_FILE)
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__

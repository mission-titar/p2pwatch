from datetime import timedelta
from pathlib import PurePath
from typing import Any

import pytest

from p2pwatch.adapters.driven.config.crawler_config_schema import crawler_config_from_document
from p2pwatch.domain.crawler_config import (
    BackoffConfig,
    CrawlerConfig,
    ObservabilityConfig,
    SearchConfig,
    WebuiConfig,
)
from p2pwatch.domain.invalid_config import InvalidConfigError

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
    "key", ["shutdown_deadline_seconds", "amule_api_password", "catalog_db_path", "local_db_path"]
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


def test_the_root_backoff_is_refused_with_its_new_place() -> None:
    document = _document() | {"backoff": _document()["search"]["backoff"]}
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
        "port_sync",
        "amules",
        "observability.log_level",
        "download.enabled",
        "webui.amule_url",
    ]

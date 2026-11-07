from pathlib import PurePath
from typing import Any

import pytest

from p2pwatch.adapters.driven.config.crawler_config_schema import crawler_config_from_document
from p2pwatch.domain.crawler_config import parse_crawler_config
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
    config = crawler_config_from_document(_document(), file_path=_FILE)
    assert config == parse_crawler_config(_document())


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


def test_every_key_nothing_reads_is_listed_beside_the_parses_problem() -> None:
    document = _document() | {"port_sync": {"enabled": True}, "amules": [], "webui": []}
    assert _problems(document) == [
        ("port_sync", "was removed, delete it from crawler.yml"),
        ("amules", "Extra inputs are not permitted"),
        ("webui", "mapping expected, got list"),
    ]

from datetime import date
from pathlib import PurePath
from typing import Any

import pytest

from p2pwatch.adapters.driven.config.interpolation import InterpolatedDocument, interpolate_document
from p2pwatch.domain.config_problem import ConfigProblem

_PATH = PurePath("/srv/crawler.yml")


def _resolved(document: dict[str, Any], *, env: dict[str, str]) -> dict[str, Any]:
    interpolated = interpolate_document(document, env=env, file_path=_PATH)
    assert interpolated.problems == ()
    return interpolated.document


def test_a_string_without_a_reference_is_unchanged() -> None:
    document = {"catalog_db_path": "/data/catalog.db", "note": "price is $5"}
    assert _resolved(document, env={}) == document


def test_each_reference_in_a_string_is_replaced_by_its_variable() -> None:
    document = {"url": "discord://${ID}/${TOKEN}", "twice": "${ID}-${ID}"}
    env = {"ID": "111", "TOKEN": "xyz"}
    assert _resolved(document, env=env) == {
        "url": "discord://111/xyz",
        "twice": "111-111",
    }


def test_every_string_value_is_resolved_however_deep() -> None:
    document = {
        "search": {"keywords": ["${KEYWORD}", "titar"]},
        "observability": {"notifications": [{"url": "${URL}", "audience": "${AUDIENCE}"}]},
    }
    env = {"KEYWORD": "keroro", "URL": "discord://a", "AUDIENCE": "community"}
    assert _resolved(document, env=env) == {
        "search": {"keywords": ["keroro", "titar"]},
        "observability": {"notifications": [{"url": "discord://a", "audience": "community"}]},
    }


def test_a_key_is_never_resolved_since_it_names_the_schema() -> None:
    assert _resolved({"webui": {"${A}": "x"}}, env={"A": "amule_url"}) == {"webui": {"${A}": "x"}}


def test_a_value_that_is_no_string_is_unchanged() -> None:
    document: dict[str, Any] = {
        "port": 9100,
        "ratio": 0.3,
        "enabled": True,
        "node_id": None,
        "aired": date(2008, 1, 7),
    }
    assert _resolved(document, env={}) == document


@pytest.mark.parametrize(
    ("document", "key_path"),
    [
        ({"amule_api_password": "${UNSET}"}, "amule_api_password"),
        ({"webui": {"amule_url": "http://${UNSET}"}}, "webui.amule_url"),
        ({"search": {"keywords": ["keroro", "${UNSET}"]}}, "search.keywords[1]"),
        (
            {"observability": {"notifications": [{"url": "${UNSET}"}]}},
            "observability.notifications[0].url",
        ),
        ({"matrix": [["${UNSET}"]]}, "matrix[0][0]"),
    ],
)
def test_an_unset_variable_is_a_problem_under_its_key_path_its_reference_left_as_written(
    *, document: dict[str, Any], key_path: str
) -> None:
    assert interpolate_document(
        document, env={"SET": "x"}, file_path=_PATH
    ) == InterpolatedDocument(
        document=document,
        problems=(
            ConfigProblem(
                file_path=_PATH,
                key=key_path,
                message="environment variable 'UNSET' referenced but not set",
            ),
        ),
    )


def test_every_unset_or_ill_formed_variable_is_a_problem_in_the_documents_order() -> None:
    document = {
        "amule_api_password": "${PASSWORD}",
        "search": {"keywords": ["${KEYWORD}", "${SET}"]},
        "webui": {"amule_url": "http://${HOST}"},
    }

    interpolated = interpolate_document(
        document, env={"SET": "titar", "KEYWORD": "\udcff"}, file_path=_PATH
    )

    assert [(problem.key, problem.message) for problem in interpolated.problems] == [
        ("amule_api_password", "environment variable 'PASSWORD' referenced but not set"),
        ("search.keywords[0]", "environment variable 'KEYWORD' is not valid UTF-8"),
        ("webui.amule_url", "environment variable 'HOST' referenced but not set"),
    ]
    assert interpolated.document["search"] == {"keywords": ["${KEYWORD}", "titar"]}


# ``os.environ`` decodes a byte that is not UTF-8 as a lone surrogate (``surrogateescape``).
@pytest.mark.parametrize("value", ["\udcff", "keroro\ud800"])
def test_a_variable_that_is_not_utf8_is_a_problem_under_its_key_path_naming_it(value: str) -> None:
    interpolated = interpolate_document(
        {"search": {"keywords": ["${KEYWORD}"]}}, env={"KEYWORD": value}, file_path=_PATH
    )
    assert interpolated.problems == (
        ConfigProblem(
            file_path=_PATH,
            key="search.keywords[0]",
            message="environment variable 'KEYWORD' is not valid UTF-8",
        ),
    )


def test_a_variable_no_value_references_is_never_checked() -> None:
    document = {"url": "${SET}"}
    assert _resolved(document, env={"SET": "x", "OTHER": "\udcff"}) == {"url": "x"}

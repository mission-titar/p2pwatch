from datetime import date
from typing import Any

import pytest

from p2pwatch.adapters.driven.config.errors import ConfigError
from p2pwatch.adapters.driven.config.interpolation import interpolate_document


def test_a_string_without_a_reference_is_unchanged() -> None:
    document = {"catalog_db_path": "/data/catalog.db", "note": "price is $5"}
    assert interpolate_document(document, {}) == document


def test_each_reference_in_a_string_is_replaced_by_its_variable() -> None:
    document = {"url": "discord://${ID}/${TOKEN}", "twice": "${ID}-${ID}"}
    env = {"ID": "111", "TOKEN": "xyz"}
    assert interpolate_document(document, env) == {"url": "discord://111/xyz", "twice": "111-111"}


def test_every_string_value_is_resolved_however_deep() -> None:
    document = {
        "search": {"keywords": ["${KEYWORD}", "titar"]},
        "observability": {"notifications": [{"url": "${URL}", "audience": "${AUDIENCE}"}]},
    }
    env = {"KEYWORD": "keroro", "URL": "discord://a", "AUDIENCE": "community"}
    assert interpolate_document(document, env) == {
        "search": {"keywords": ["keroro", "titar"]},
        "observability": {"notifications": [{"url": "discord://a", "audience": "community"}]},
    }


def test_a_key_is_never_resolved_since_it_names_the_schema() -> None:
    assert interpolate_document({"webui": {"${A}": "x"}}, {"A": "amule_url"}) == {
        "webui": {"${A}": "x"}
    }


def test_a_value_that_is_no_string_is_unchanged() -> None:
    document: dict[str, Any] = {
        "port": 9100,
        "ratio": 0.3,
        "enabled": True,
        "node_id": None,
        "aired": date(2008, 1, 7),
    }
    assert interpolate_document(document, {}) == document


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
def test_an_unset_variable_is_refused_under_its_key_path(
    document: dict[str, Any], key_path: str
) -> None:
    with pytest.raises(ConfigError) as error:
        interpolate_document(document, {"SET": "x"})
    assert error.value.key == key_path
    assert error.value.message == "environment variable 'UNSET' referenced but not set"

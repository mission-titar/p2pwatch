import dataclasses
import re
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from catalog_matching.validation import parse_matcher_config, parse_targets
from p2pwatch.adapters.config.crawler_config import (
    BackoffConfig,
    ConfigError,
    CrawlerConfig,
    DownloadConfig,
    LoadedConfig,
    MetricsConfig,
    NotificationTarget,
    ObservabilityConfig,
    SearchConfig,
    WebuiConfig,
    load_config,
    parse_crawler_config,
)
from p2pwatch.adapters.config.yaml_loader import load_yaml
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.policy_fingerprint import policy_fingerprint

_DEPLOY = Path(__file__).resolve().parents[5] / "deploy"


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


def _env() -> dict[str, str]:
    return {"AMULE_API_PASSWORD": "s3cr3t"}


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


def _section(raw: dict[str, Any], path: str | None) -> dict[str, Any]:
    """The mapping at the dotted ``path`` of ``raw``, ``raw`` itself for ``None``."""
    for name in path.split(".") if path else ():
        raw = raw[name]
    return raw


def _printed_path(section: str | None, key: str) -> str:
    """The pattern of ``key``'s path in an error: a root key prints bare."""
    return re.escape(f"{section}.{key}" if section else key)


# --------------------------------------------------------------------- policy


def test_parses_a_valid_config() -> None:
    config = parse_crawler_config(_minimal_raw(), _env())
    assert config == CrawlerConfig(
        search=SearchConfig(
            keywords=("keroro", "titar"),
            backoff=BackoffConfig(
                base_seconds=2.0, cap_seconds=300.0, factor=2.0, jitter_ratio=0.3
            ),
        ),
        shutdown_deadline_seconds=10.0,
        amule_api_password="secret",
        catalog_db_path="/data/catalog.db",
        local_db_path="/data/local.db",
        node_id=None,
        download=None,
    )


def test_jitter_ratio_zero_is_accepted() -> None:
    raw = _minimal_raw()
    raw["search"]["backoff"]["jitter_ratio"] = 0.0  # 0 = no jitter (≥ 0 allowed)
    assert parse_crawler_config(raw, _env()).search.backoff.jitter_ratio == 0.0


def test_negative_jitter_ratio_is_fatal() -> None:
    raw = _minimal_raw()
    raw["search"]["backoff"]["jitter_ratio"] = -0.1
    with pytest.raises(ConfigError, match="≥ 0 expected"):
        parse_crawler_config(raw, _env())


def test_missing_key_is_fatal() -> None:
    raw = _minimal_raw()
    del raw["shutdown_deadline_seconds"]
    with pytest.raises(ConfigError, match=r"^key 'shutdown_deadline_seconds' missing$"):
        parse_crawler_config(raw, _env())


def test_non_numeric_value_is_fatal() -> None:
    raw = _minimal_raw()
    raw["shutdown_deadline_seconds"] = "souvent"
    with pytest.raises(ConfigError, match="number expected"):
        parse_crawler_config(raw, _env())


def test_bool_is_not_accepted_as_a_number() -> None:
    raw = _minimal_raw()
    raw["shutdown_deadline_seconds"] = True
    with pytest.raises(ConfigError, match="number expected"):
        parse_crawler_config(raw, _env())


@pytest.mark.parametrize("value", [float("inf"), float("nan")], ids=["inf", "nan"])
@pytest.mark.parametrize(
    ("section", "key"),
    [
        ("search.backoff", "base_seconds"),
        ("search.backoff", "cap_seconds"),
        ("search.backoff", "factor"),
        ("search.backoff", "jitter_ratio"),
        ("observability", "notification_timeout_seconds"),
        ("download", "poll_interval_seconds"),
        ("download", "lost_after_seconds"),
        ("download", "reappeared_after_seconds"),
        ("download", "sources_interval_seconds"),
        (None, "shutdown_deadline_seconds"),
    ],
)
def test_a_number_that_is_not_finite_is_refused_by_name(
    section: str | None, key: str, value: float
) -> None:
    # .inf would make a sleep endless and .nan passes every comparison.
    raw = _minimal_raw() | {"download": _full_download_section(), "observability": {}}
    _section(raw, section)[key] = value
    with pytest.raises(
        ConfigError, match=rf"^{_printed_path(section, key)}: finite number expected"
    ):
        parse_crawler_config(raw, _env())


def _with_seconds(section: str | None, key: str, seconds: int) -> dict[str, Any]:
    """A full config whose ``key`` holds ``seconds``, the backoff's cap above any floor."""
    raw = _minimal_raw() | {"download": _full_download_section(), "observability": {}, "webui": {}}
    raw["search"]["backoff"]["cap_seconds"] = 86_400
    _section(raw, section)[key] = seconds
    return raw


@pytest.mark.parametrize(
    ("section", "key"),
    [
        ("download", "poll_interval_seconds"),
        ("download", "sources_interval_seconds"),
        ("webui", "source_period_gap_seconds"),
        ("search.backoff", "base_seconds"),
        ("search.backoff", "cap_seconds"),
        ("observability", "notification_timeout_seconds"),
        (None, "shutdown_deadline_seconds"),
    ],
)
def test_a_duration_is_at_most_a_day(section: str | None, key: str) -> None:
    parse_crawler_config(_with_seconds(section, key, 86_400), _env())
    with pytest.raises(
        ConfigError,
        match=rf"^{_printed_path(section, key)}: at most 86400 seconds expected, got 86401",
    ):
        parse_crawler_config(_with_seconds(section, key, 86_401), _env())


@pytest.mark.parametrize("key", ["lost_after_seconds", "reappeared_after_seconds"])
def test_an_absence_is_at_most_thirty_days(key: str) -> None:
    parse_crawler_config(_with_seconds("download", key, 2_592_000), _env())
    with pytest.raises(
        ConfigError, match=rf"download\.{key}: at most 2592000 seconds expected, got 2592001"
    ):
        parse_crawler_config(_with_seconds("download", key, 2_592_001), _env())


def test_non_positive_value_is_fatal() -> None:
    raw = _minimal_raw()
    raw["shutdown_deadline_seconds"] = 0
    with pytest.raises(ConfigError, match="strictly positive"):
        parse_crawler_config(raw, _env())


@pytest.mark.parametrize(
    "key",
    [
        "cycle_interval_seconds",
        "decision_poll_interval_seconds",
        "keyword_pause_max_seconds",
        "keyword_pause_min_seconds",
        "port_sync",
        "search_poll_budget_seconds",
        "search_poll_interval_seconds",
    ],
)
def test_a_removed_key_is_refused_by_name(key: str) -> None:
    raw = _minimal_raw() | {key: 5.0}
    with pytest.raises(
        ConfigError, match=rf"^key '{key}' was removed, delete it from crawler\.yml$"
    ):
        parse_crawler_config(raw, _env())


def test_the_root_backoff_is_refused_with_its_new_place() -> None:
    raw = _minimal_raw() | {"backoff": _minimal_raw()["search"]["backoff"]}
    with pytest.raises(
        ConfigError,
        match=r"^key 'backoff' moved to 'search\.backoff', move it in crawler\.yml$",
    ):
        parse_crawler_config(raw, _env())


def test_a_missing_backoff_is_fatal() -> None:
    raw = _minimal_raw()
    del raw["search"]["backoff"]
    with pytest.raises(ConfigError, match=r"search\.backoff: key '\w+' missing"):
        parse_crawler_config(raw, _env())


def test_backoff_section_must_be_a_mapping() -> None:
    raw = _minimal_raw()
    raw["search"]["backoff"] = [1, 2, 3]
    with pytest.raises(ConfigError, match=r"section 'search\.backoff'"):
        parse_crawler_config(raw, _env())


def test_backoff_factor_below_one_is_fatal() -> None:
    raw = _minimal_raw()
    raw["search"]["backoff"]["factor"] = 0.5
    with pytest.raises(ConfigError, match=r"search\.backoff\.factor must be ≥ 1"):
        parse_crawler_config(raw, _env())


def test_backoff_cap_below_base_is_fatal() -> None:
    raw = _minimal_raw()
    raw["search"]["backoff"]["cap_seconds"] = 1.0
    raw["search"]["backoff"]["base_seconds"] = 10.0
    with pytest.raises(ConfigError, match=r"search\.backoff\.cap_seconds .* cap below floor"):
        parse_crawler_config(raw, _env())


# ------------------------------------------------------------------------- the single amuled


def test_node_id_override_is_kept() -> None:
    raw = _minimal_raw()
    raw["node_id"] = "fixed-node"
    assert parse_crawler_config(raw, _env()).node_id == "fixed-node"


def test_missing_amule_api_password_is_fatal() -> None:
    raw = _minimal_raw()
    del raw["amule_api_password"]
    with pytest.raises(ConfigError, match=r"^key 'amule_api_password' missing$"):
        parse_crawler_config(raw, _env())


def test_empty_amule_api_password_is_fatal() -> None:
    raw = _minimal_raw() | {"amule_api_password": ""}
    with pytest.raises(
        ConfigError, match=r"^amule_api_password: non-empty string expected, got ''$"
    ):
        parse_crawler_config(raw, _env())


def test_non_string_amule_api_password_is_fatal() -> None:
    raw = _minimal_raw() | {"amule_api_password": 1234}
    with pytest.raises(
        ConfigError, match=r"^amule_api_password: non-empty string expected, got 1234$"
    ):
        parse_crawler_config(raw, _env())


def test_leftover_pool_keys_are_ignored() -> None:
    # The live-node migration edits crawler.yml by hand (design §11). An operator who forgets to
    # delete the old pool keys must still get a bootable crawler, not a fail-fast on a dead key.
    raw = _minimal_raw() | {
        "amules": [{"name": "amule-1", "host": "amuled", "port": 4712, "password": "x"}],
    }
    assert parse_crawler_config(raw, _env()).amule_api_password == "secret"


def test_missing_db_path_is_fatal() -> None:
    raw = _minimal_raw()
    del raw["catalog_db_path"]
    with pytest.raises(ConfigError, match=r"^key 'catalog_db_path' missing$"):
        parse_crawler_config(raw, _env())


def test_empty_node_id_string_is_fatal() -> None:
    raw = _minimal_raw()
    raw["node_id"] = ""
    with pytest.raises(ConfigError, match="node_id"):
        parse_crawler_config(raw, _env())


# ----------------------------------------------------------- interpolation ${}


def test_password_interpolated_from_env() -> None:
    # The domain never reads the environment: the adapter resolves ${NAME} before anything else
    # sees the value (design §6).
    raw = _minimal_raw() | {"amule_api_password": "${AMULE_API_PASSWORD}"}
    cfg = parse_crawler_config(raw, {"AMULE_API_PASSWORD": "s3cr3t"})
    assert cfg.amule_api_password == "s3cr3t"


def test_missing_env_var_raises() -> None:
    raw = _minimal_raw() | {"amule_api_password": "${AMULE_API_PASSWORD}"}
    with pytest.raises(
        ConfigError,
        match=r"^amule_api_password: environment variable 'AMULE_API_PASSWORD' "
        r"referenced but not set$",
    ):
        parse_crawler_config(raw, {})  # AMULE_API_PASSWORD not set


# ----------------------------------------------------------------- download


def test_download_absent_is_observer() -> None:
    cfg = parse_crawler_config(_minimal_raw(), _env())
    assert cfg.download is None


def test_download_enabled_false_is_observer_without_requiring_wiring() -> None:
    # enabled:false ⇒ we do NOT read the rest: a missing poll_interval is NOT an error.
    raw = _minimal_raw() | {"download": {"enabled": False}}
    cfg = parse_crawler_config(raw, _env())
    assert cfg.download is None


def test_download_section_without_enabled_defaults_to_observer() -> None:
    # enabled missing → default false → download None (missing-key branch of _bool_default).
    raw = _minimal_raw() | {"download": {"poll_interval_seconds": 30.0}}
    assert parse_crawler_config(raw, _env()).download is None


def test_download_enabled_non_bool_is_fatal() -> None:
    raw = _minimal_raw() | {"download": {"enabled": "oui"}}
    with pytest.raises(ConfigError, match="boolean expected"):
        parse_crawler_config(raw, _env())


def test_download_section_must_be_a_mapping() -> None:
    raw = _minimal_raw() | {"download": [1, 2]}
    with pytest.raises(ConfigError, match="section 'download'"):
        parse_crawler_config(raw, _env())


def test_download_enabled_true_requires_the_poll_interval() -> None:
    raw = _minimal_raw() | {"download": {"enabled": True, "min_free_bytes": 1024}}
    with pytest.raises(ConfigError, match="poll_interval_seconds"):
        parse_crawler_config(raw, _env())


def test_download_enabled_true_full_is_download_mode() -> None:
    raw = _minimal_raw() | {"download": _full_download_section()}
    cfg = parse_crawler_config(raw, _env())
    assert cfg.download == DownloadConfig(
        poll_interval_seconds=30.0,
        min_free_bytes=1_000_000_000,
        lost_after=timedelta(hours=1),
        output_dir="/data/out",
        reappeared_after=timedelta(seconds=5400),
        sources_interval=timedelta(seconds=120),
    )


def test_the_sources_are_read_a_poll_after_their_interval() -> None:
    # The step runs on the first round past its interval (source points spec, D3).
    raw = _minimal_raw() | {"download": _full_download_section()}
    cfg = parse_crawler_config(raw, _env())
    assert cfg.download is not None
    assert cfg.download.time_between_source_reads == timedelta(seconds=150)


def test_download_sources_interval_defaults_to_five_minutes() -> None:
    section = _full_download_section()
    del section["sources_interval_seconds"]
    cfg = parse_crawler_config(_minimal_raw() | {"download": section}, _env())
    assert cfg.download is not None
    assert cfg.download.sources_interval == timedelta(seconds=300)


@pytest.mark.parametrize("seconds", [0, -1, float("inf"), float("nan")])
def test_download_sources_interval_is_a_positive_finite_number(seconds: float) -> None:
    section = _full_download_section() | {"sources_interval_seconds": seconds}
    with pytest.raises(ConfigError, match=r"download\.sources_interval_seconds"):
        parse_crawler_config(_minimal_raw() | {"download": section}, _env())


def test_download_poll_interval_must_be_positive() -> None:
    section = _full_download_section() | {"poll_interval_seconds": 0.0}
    raw = _minimal_raw() | {"download": section}
    with pytest.raises(ConfigError, match="strictly positive"):
        parse_crawler_config(raw, _env())


def test_download_min_free_must_be_positive_integer() -> None:
    section = _full_download_section() | {"min_free_bytes": 0}
    raw = _minimal_raw() | {"download": section}
    with pytest.raises(ConfigError, match="strictly positive"):
        parse_crawler_config(raw, _env())


def test_download_lost_after_must_be_positive() -> None:
    section = _full_download_section() | {"lost_after_seconds": 0.0}
    raw = _minimal_raw() | {"download": section}
    with pytest.raises(ConfigError, match="strictly positive"):
        parse_crawler_config(raw, _env())


def test_download_space_and_ttl_knobs_have_defaults() -> None:
    # All three are new in 2026-09-13: an operator config predating them must still boot, so
    # they default instead of failing fast like the older required keys.
    section = _full_download_section()
    for key in ("min_free_bytes", "lost_after_seconds", "output_dir"):
        del section[key]
    raw = _minimal_raw() | {"download": section}
    cfg = parse_crawler_config(raw, _env())
    assert cfg.download is not None
    assert cfg.download.min_free_bytes == 10_737_418_240  # 10 GiB
    assert cfg.download.lost_after == timedelta(hours=24)
    assert cfg.download.output_dir == "/downloads"  # what deploy/compose.yml mounts


def test_a_source_reappears_after_12_hours_by_default() -> None:
    section = _full_download_section()
    del section["reappeared_after_seconds"]
    cfg = parse_crawler_config(_minimal_raw() | {"download": section}, _env())
    assert cfg.download is not None
    assert cfg.download.reappeared_after == timedelta(hours=12)


@pytest.mark.parametrize("seconds", [0, -1, float("inf"), float("nan"), 1e15])
def test_reappeared_after_seconds_is_a_positive_finite_duration(seconds: float) -> None:
    # .inf overflows a duration and .nan would silently disable the event (D9).
    section = _full_download_section() | {"reappeared_after_seconds": seconds}
    with pytest.raises(ConfigError, match=r"download\.reappeared_after_seconds"):
        parse_crawler_config(_minimal_raw() | {"download": section}, _env())


def test_download_output_dir_must_be_a_string() -> None:
    section = _full_download_section() | {"output_dir": 42}
    raw = _minimal_raw() | {"download": section}
    with pytest.raises(ConfigError, match="output_dir"):
        parse_crawler_config(raw, _env())


# ------------------------------------------------------------------- search


def test_a_missing_search_section_is_fatal() -> None:
    raw = _minimal_raw()
    del raw["search"]
    with pytest.raises(ConfigError, match="search: key 'keywords' missing"):
        parse_crawler_config(raw, {})


def test_missing_search_keywords_are_fatal() -> None:
    raw = _minimal_raw()
    del raw["search"]["keywords"]
    with pytest.raises(ConfigError, match="search: key 'keywords' missing"):
        parse_crawler_config(raw, {})


def test_search_keywords_read_from_section() -> None:
    raw = _minimal_raw()
    raw["search"]["keywords"] = ["keroro", "titar", "mission titar"]
    config = parse_crawler_config(raw, {})
    assert config.search.keywords == ("keroro", "titar", "mission titar")


def test_search_keywords_rejects_empty_list() -> None:
    raw = _minimal_raw()
    raw["search"]["keywords"] = []
    with pytest.raises(ConfigError, match=r"search\.keywords: non-empty list"):
        parse_crawler_config(raw, {})


def test_search_keywords_rejects_non_string_entry() -> None:
    raw = _minimal_raw()
    raw["search"]["keywords"] = ["keroro", 42]
    with pytest.raises(ConfigError, match=r"search\.keywords: non-empty string expected, got 42"):
        parse_crawler_config(raw, {})


# ----------------------------------------------------------- observability


def test_an_absent_observability_logs_at_info_with_no_metrics_and_no_notification() -> None:
    assert parse_crawler_config(_minimal_raw(), _env()).observability == ObservabilityConfig(
        log_level="INFO", metrics=None, notification_timeout_seconds=5.0, notifications=()
    )


@pytest.mark.parametrize(
    ("metrics", "port"),
    [
        (MetricsConfig(enabled=True, port=9100), 9100),
        (MetricsConfig(enabled=False, port=9100), None),
        (None, None),
    ],
)
def test_the_metrics_port_is_the_configured_one_only_when_enabled(
    metrics: MetricsConfig | None, port: int | None
) -> None:
    observability = ObservabilityConfig(
        log_level="INFO", metrics=metrics, notification_timeout_seconds=5.0, notifications=()
    )
    assert observability.metrics_port == port


def test_observability_parsed() -> None:
    raw = _minimal_raw() | {
        "observability": {
            "log_level": "DEBUG",
            "metrics": {"enabled": True, "port": 9100},
            "notification_timeout_seconds": 3.0,
        }
    }
    cfg = parse_crawler_config(raw, _env())
    assert cfg.observability == ObservabilityConfig(
        log_level="DEBUG",
        metrics=MetricsConfig(enabled=True, port=9100),
        notification_timeout_seconds=3.0,
        notifications=(),
    )


def test_observability_metrics_optional() -> None:
    raw = _minimal_raw() | {"observability": {"log_level": "INFO"}}
    cfg = parse_crawler_config(raw, _env())
    assert cfg.observability == ObservabilityConfig(
        log_level="INFO", metrics=None, notification_timeout_seconds=5.0, notifications=()
    )


def test_observability_bad_log_level_rejected() -> None:
    raw = _minimal_raw() | {"observability": {"log_level": "LOUD"}}
    with pytest.raises(ConfigError, match="log_level"):
        parse_crawler_config(raw, _env())


def test_observability_metrics_enabled_key_missing_rejected() -> None:
    raw = _minimal_raw() | {"observability": {"log_level": "INFO", "metrics": {"port": 9100}}}
    with pytest.raises(ConfigError, match="'enabled' missing"):
        parse_crawler_config(raw, _env())


def test_observability_metrics_port_key_missing_rejected() -> None:
    # missing-key branch of _positive_int (the only required caller left since the download
    # knobs gained defaults).
    raw = _minimal_raw() | {"observability": {"log_level": "INFO", "metrics": {"enabled": True}}}
    with pytest.raises(ConfigError, match="port"):
        parse_crawler_config(raw, _env())


def test_observability_metrics_enabled_non_bool_rejected() -> None:
    raw = _minimal_raw() | {
        "observability": {"log_level": "INFO", "metrics": {"enabled": 1, "port": 9100}}
    }
    with pytest.raises(ConfigError, match="boolean expected"):
        parse_crawler_config(raw, _env())


def test_notifications_absent_is_empty() -> None:
    raw = _minimal_raw() | {"observability": {"log_level": "INFO"}}
    cfg = parse_crawler_config(raw, _env())
    assert cfg.observability is not None
    assert cfg.observability.notifications == ()


def test_notifications_parsed() -> None:
    raw = _minimal_raw() | {
        "observability": {
            "log_level": "INFO",
            "notifications": [
                {"url": "discord://a", "audience": "community", "node_prefix": False},
                {"url": "discord://b", "audience": "operations"},
            ],
        }
    }
    cfg = parse_crawler_config(raw, _env())
    assert cfg.observability is not None
    assert cfg.observability.notifications == (
        NotificationTarget(url="discord://a", audience=Audience.COMMUNITY, node_prefix=False),
        NotificationTarget(url="discord://b", audience=Audience.OPERATIONS, node_prefix=True),
    )


def test_notification_node_prefix_non_bool_rejected() -> None:
    raw = _minimal_raw() | {
        "observability": {
            "log_level": "INFO",
            "notifications": [{"url": "x", "audience": "community", "node_prefix": "no"}],
        }
    }
    with pytest.raises(ConfigError, match=r"notifications\[0\]\.node_prefix: boolean expected"):
        parse_crawler_config(raw, _env())


def test_notifications_bad_audience_rejected() -> None:
    raw = _minimal_raw() | {
        "observability": {
            "log_level": "INFO",
            "notifications": [{"url": "x", "audience": "nope"}],
        }
    }
    with pytest.raises(
        ConfigError, match=r"notifications\[0\]\.audience: 'community' or 'operations' expected"
    ):
        parse_crawler_config(raw, _env())


@pytest.mark.parametrize(
    "target",
    [
        {"url": "x", "tag": "community"},
        {"url": "x", "tag": "community", "audience": "community"},
    ],
)
def test_a_notification_tag_is_refused_with_its_new_name(target: dict[str, str]) -> None:
    raw = _minimal_raw() | {"observability": {"log_level": "INFO", "notifications": [target]}}
    with pytest.raises(ConfigError, match=r"notifications\[0\]: key 'tag' was renamed 'audience'"):
        parse_crawler_config(raw, _env())


def test_notification_url_interpolated_substring() -> None:
    raw = _minimal_raw() | {
        "observability": {
            "log_level": "INFO",
            "notifications": [{"url": "discord://${WID}/${WTOK}", "audience": "operations"}],
        }
    }
    cfg = parse_crawler_config(raw, _env() | {"WID": "1", "WTOK": "t"})
    assert cfg.observability is not None
    assert cfg.observability.notifications[0].url == "discord://1/t"


# ------------------------------------------------------------------- webui


def test_webui_absent_defaults_to_enabled() -> None:
    # No webui section → the in-process webui is ON by default. The bind is fixed at
    # 0.0.0.0:8080 in the composition layer; it is NOT configurable here.
    cfg = parse_crawler_config(_minimal_raw(), _env())
    assert cfg.webui == WebuiConfig(enabled=True)


def test_webui_enabled_false_disables_the_surface() -> None:
    raw = _minimal_raw() | {"webui": {"enabled": False}}
    assert parse_crawler_config(raw, _env()).webui == WebuiConfig(enabled=False)


def test_webui_host_and_port_are_silently_ignored() -> None:
    # A legacy config still carrying host/port must NOT fail: those keys are simply not read
    # (the bind is fixed in code). The result carries only `enabled`, nothing else.
    raw = _minimal_raw() | {"webui": {"enabled": True, "host": "1.2.3.4", "port": 9999}}
    cfg = parse_crawler_config(raw, _env())
    assert cfg.webui == WebuiConfig(enabled=True)
    # the type no longer carries a bind
    assert {field.name for field in dataclasses.fields(WebuiConfig)}.isdisjoint({"host", "port"})


def test_webui_enabled_defaults_true_when_key_absent_in_section() -> None:
    # Section present (with a now-ignored host) but no `enabled` key → default True
    # (missing-key branch of _bool_default); the host is ignored.
    raw = _minimal_raw() | {"webui": {"host": "1.2.3.4"}}
    assert parse_crawler_config(raw, _env()).webui == WebuiConfig(enabled=True)


def test_webui_section_must_be_a_mapping() -> None:
    raw = _minimal_raw() | {"webui": [1, 2]}
    with pytest.raises(ConfigError, match="section 'webui'"):
        parse_crawler_config(raw, _env())


def test_webui_enabled_non_bool_is_fatal() -> None:
    raw = _minimal_raw() | {"webui": {"enabled": "yes"}}
    with pytest.raises(ConfigError, match="boolean expected"):
        parse_crawler_config(raw, _env())


def test_webui_amule_url_defaults_to_the_published_port() -> None:
    # Both web surfaces are published by default (design §9): p2pwatch on 8080, amuleweb on
    # 4711. The default is the no-proxy case; anything else is the operator's to set.
    assert parse_crawler_config(_minimal_raw(), _env()).webui.amule_url == "http://localhost:4711"


def test_webui_amule_url_is_configurable_for_a_reverse_proxy() -> None:
    # The link must survive a reverse proxy in front of 8080, which is the whole point of the key.
    raw = _minimal_raw() | {"webui": {"amule_url": "https://mule.example.org/amule"}}
    assert parse_crawler_config(raw, _env()).webui.amule_url == "https://mule.example.org/amule"


def test_webui_amule_url_is_interpolated_from_env() -> None:
    raw = _minimal_raw() | {"webui": {"amule_url": "${AMULE_UI_URL}"}}
    cfg = parse_crawler_config(raw, _env() | {"AMULE_UI_URL": "http://nas.lan:4711"})
    assert cfg.webui.amule_url == "http://nas.lan:4711"


@pytest.mark.parametrize("webui", [None, {"enabled": True}], ids=["no-section", "no-key"])
def test_webui_source_period_gap_defaults_to_the_writers_tolerance_at_the_shipped_defaults(
    webui: dict[str, Any] | None,
) -> None:
    # 3 x (300 + 30): three reads' spacing at the shipped intervals (source points spec, D6).
    raw = _minimal_raw() if webui is None else _minimal_raw() | {"webui": webui}
    cfg = parse_crawler_config(raw, _env())
    assert cfg.webui.source_period_gap == timedelta(seconds=990)


def test_webui_source_period_gap_is_configurable() -> None:
    raw = _minimal_raw() | {"webui": {"source_period_gap_seconds": 600}}
    assert parse_crawler_config(raw, _env()).webui.source_period_gap == timedelta(seconds=600)


@pytest.mark.parametrize("seconds", [0, -1, float("inf"), float("nan")])
def test_webui_source_period_gap_is_a_positive_finite_number(seconds: float) -> None:
    raw = _minimal_raw() | {"webui": {"source_period_gap_seconds": seconds}}
    with pytest.raises(ConfigError, match=r"webui\.source_period_gap_seconds"):
        parse_crawler_config(raw, _env())


def test_webui_amule_url_empty_is_fatal() -> None:
    raw = _minimal_raw() | {"webui": {"amule_url": ""}}
    with pytest.raises(ConfigError, match="non-empty string"):
        parse_crawler_config(raw, _env())


# ------------------------------------------------------------- the three files


def _write_crawler_config(tmp_path: Path) -> Path:
    path = tmp_path / "crawler.yml"
    path.write_text(
        "shutdown_deadline_seconds: 10.0\n"
        "search:\n"
        "  keywords: [keroro]\n"
        "  backoff: {base_seconds: 2.0, cap_seconds: 300.0, factor: 2.0, jitter_ratio: 0.3}\n"
        "amule_api_password: ${AMULE_API_PASSWORD}\n"
        "catalog_db_path: /data/catalog.db\n"
        "local_db_path: /data/local.db\n",
        encoding="utf-8",
    )
    return path


def test_the_three_files_load_with_the_fingerprint_of_the_policy(tmp_path: Path) -> None:
    config_path = _write_crawler_config(tmp_path)
    targets_path, matcher_path = _DEPLOY / "targets.yml", _DEPLOY / "matcher.yml"

    loaded = load_config(config_path, targets_path, matcher_path, _env())

    assert loaded == LoadedConfig(
        crawler_config=parse_crawler_config(load_yaml(config_path), _env()),
        targets=parse_targets(load_yaml(targets_path)),
        matcher_config=parse_matcher_config(load_yaml(matcher_path)),
        policy_fingerprint=policy_fingerprint(matcher_path.read_bytes(), targets_path.read_bytes()),
    )


@pytest.mark.parametrize(
    ("broken_file", "text"),
    [
        ("crawler.yml", "search: [unclosed\n"),  # a YAML that does not load
        ("crawler.yml", "catalog_db_path: c\n"),  # a key that does not parse
        ("targets.yml", "episodes: nope\n"),  # the matching's own error
        ("matcher.yml", "tokens: {}\nrules: {}\n"),
    ],
)
def test_an_invalid_file_is_an_invalid_config(tmp_path: Path, broken_file: str, text: str) -> None:
    paths = {
        "crawler.yml": _write_crawler_config(tmp_path),
        "targets.yml": _DEPLOY / "targets.yml",
        "matcher.yml": _DEPLOY / "matcher.yml",
    }
    paths[broken_file] = tmp_path / f"broken-{broken_file}"
    paths[broken_file].write_text(text, encoding="utf-8")

    with pytest.raises(InvalidConfigError):
        load_config(paths["crawler.yml"], paths["targets.yml"], paths["matcher.yml"], _env())

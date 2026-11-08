from pathlib import Path

import pytest

from p2pwatch.adapters.driven.config.crawler_config import load_config, read_crawler_config
from p2pwatch.adapters.driven.config.crawler_config_schema import crawler_config_from_document
from p2pwatch.adapters.driven.config.interpolation import interpolate_document
from p2pwatch.adapters.driven.config.matcher_config_schema import matcher_config_from_document
from p2pwatch.adapters.driven.config.targets_schema import targets_from_document
from p2pwatch.adapters.driven.config.yaml_loader import load_yaml
from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.crawler_config import LoadedConfig
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.policy_fingerprint import policy_fingerprint

_DEPLOY = Path(__file__).resolve().parents[6] / "deploy"


def _env() -> dict[str, str]:
    return {"AMULE_API_PASSWORD": "s3cr3t"}


def _write_crawler_config(tmp_path: Path, *, keywords: str = "[keroro]", extra: str = "") -> Path:
    path = tmp_path / "crawler.yml"
    path.write_text(
        "shutdown_deadline_seconds: 10.0\n"
        "search:\n"
        f"  keywords: {keywords}\n"
        "  backoff: {base_seconds: 2.0, cap_seconds: 300.0, factor: 2.0, jitter_ratio: 0.3}\n"
        "amule_api_password: ${AMULE_API_PASSWORD}\n"
        "catalog_db_path: /data/catalog.db\n"
        f"local_db_path: /data/local.db\n{extra}",
        encoding="utf-8",
    )
    return path


def _load_with_the_shipped_policy(config_path: Path, *, env: dict[str, str]) -> LoadedConfig:
    return load_config(
        config_path,
        targets_path=_DEPLOY / "targets.yml",
        matcher_path=_DEPLOY / "matcher.yml",
        env=env,
    )


def test_the_three_files_load_with_the_fingerprint_of_the_policy(tmp_path: Path) -> None:
    config_path = _write_crawler_config(tmp_path)
    targets_path, matcher_path = _DEPLOY / "targets.yml", _DEPLOY / "matcher.yml"

    loaded = load_config(
        config_path, targets_path=targets_path, matcher_path=matcher_path, env=_env()
    )

    assert loaded == LoadedConfig(
        crawler_config=crawler_config_from_document(
            interpolate_document(
                load_yaml(config_path).document, env=_env(), file_path=config_path
            ).document,
            file_path=config_path,
        ),
        targets=targets_from_document(load_yaml(targets_path).document, file_path=targets_path),
        matcher_config=matcher_config_from_document(
            load_yaml(matcher_path).document, file_path=matcher_path
        ),
        policy_fingerprint=policy_fingerprint(
            matcher_path.read_bytes(), targets_bytes=targets_path.read_bytes()
        ),
    )


def test_a_reference_under_any_key_is_resolved_before_the_parse(tmp_path: Path) -> None:
    config_path = _write_crawler_config(tmp_path, keywords="[keroro, '${KEYWORD}']")
    loaded = _load_with_the_shipped_policy(config_path, env=_env() | {"KEYWORD": "titar"})
    assert loaded.crawler_config.search.keywords == ("keroro", "titar")


@pytest.mark.parametrize(
    ("keywords", "extra", "key_path"),
    [
        ("['${P2PWATCH_UNSET}']", "", "search.keywords[0]"),
        # Resolved everywhere, so even a section the parse skips needs its variable.
        (
            "[keroro]",
            "download: {enabled: false, output_dir: '${P2PWATCH_UNSET}'}\n",
            "download.output_dir",
        ),
    ],
    ids=["keywords", "disabled-section"],
)
def test_an_unset_variable_under_any_key_is_an_invalid_config_naming_its_key_path(
    *, tmp_path: Path, keywords: str, extra: str, key_path: str
) -> None:
    config_path = _write_crawler_config(tmp_path, keywords=keywords, extra=extra)
    with pytest.raises(InvalidConfigError) as raised:
        _load_with_the_shipped_policy(config_path, env=_env())
    assert raised.value.problems == (
        ConfigProblem(
            file_path=config_path,
            key=key_path,
            message="environment variable 'P2PWATCH_UNSET' referenced but not set",
        ),
    )


def test_no_line_prints_a_resolved_variable(tmp_path: Path) -> None:
    config_path = _write_crawler_config(
        tmp_path, extra="amule_api_pasword: ${SECRET}\nwebui: ${SECRET}\n"
    )

    with pytest.raises(InvalidConfigError) as raised:
        read_crawler_config(config_path, env=_env() | {"SECRET": "hunter2"})

    lines = [f"{problem.key}: {problem.message}" for problem in raised.value.problems]
    assert {problem.key for problem in raised.value.problems} == {"amule_api_pasword", "webui"}
    assert all("hunter2" not in line for line in lines)


@pytest.mark.parametrize(
    ("notification", "key", "message"),
    [
        (
            "{url: 'discord://${HOOK}', audience: community, tga: '${HOOK}'}",
            "observability.notifications[0].tga",
            "Extra inputs are not permitted",
        ),
        (
            "'discord://${HOOK}'",
            "observability.notifications[0]",
            "Input should be a valid dictionary",
        ),
    ],
    ids=["unknown-key", "plain-string"],
)
def test_no_line_prints_a_resolved_notification_url(
    *, tmp_path: Path, notification: str, key: str, message: str
) -> None:
    config_path = _write_crawler_config(
        tmp_path, extra=f"observability:\n  notifications: [{notification}]\n"
    )

    with pytest.raises(InvalidConfigError) as raised:
        read_crawler_config(config_path, env=_env() | {"HOOK": "1234/webhook-token"})

    [problem] = raised.value.problems
    assert (problem.key, problem.message) == (key, message)
    assert "webhook-token" not in f"{problem.key}: {problem.message}"


def test_every_unset_variable_is_listed_beside_the_parses_problem(tmp_path: Path) -> None:
    config_path = _write_crawler_config(
        tmp_path, keywords="['${KEYWORD}']", extra="webui: {amule_url: ''}\n"
    )

    with pytest.raises(InvalidConfigError) as raised:
        _load_with_the_shipped_policy(config_path, env={})

    assert [(problem.file_path, problem.key) for problem in raised.value.problems] == [
        (config_path, "search.keywords[0]"),
        (config_path, "amule_api_password"),
        (config_path, "webui.amule_url"),
    ]


@pytest.mark.parametrize(
    ("broken_file", "text", "key", "message"),
    [
        ("crawler.yml", "search: [unclosed\n", None, "invalid YAML: "),  # a broken file
        ("targets.yml", "episodes: nope\n", "episodes", "Input should be a valid list"),
        ("matcher.yml", "tokens: {}\nrules: {}\n", "rules", "Input should be a valid list"),
    ],
)
def test_an_invalid_file_is_an_invalid_config(
    *, tmp_path: Path, broken_file: str, text: str, key: str | None, message: str
) -> None:
    paths = {
        "crawler.yml": _write_crawler_config(tmp_path),
        "targets.yml": _DEPLOY / "targets.yml",
        "matcher.yml": _DEPLOY / "matcher.yml",
    }
    paths[broken_file] = tmp_path / f"broken-{broken_file}"
    paths[broken_file].write_text(text, encoding="utf-8")

    with pytest.raises(InvalidConfigError) as raised:
        load_config(
            paths["crawler.yml"],
            targets_path=paths["targets.yml"],
            matcher_path=paths["matcher.yml"],
            env=_env(),
        )

    [problem] = raised.value.problems
    assert (problem.file_path, problem.key) == (paths[broken_file], key)
    assert problem.message.startswith(message)


def test_every_wrong_file_is_listed_in_the_crawls_order(tmp_path: Path) -> None:
    config_path = _write_crawler_config(tmp_path, keywords="[]")
    targets_path = tmp_path / "absent.yml"
    matcher_path = tmp_path / "matcher.yml"
    matcher_path.write_text("tokens: {}\nrules: {}\n", encoding="utf-8")

    with pytest.raises(InvalidConfigError) as raised:
        load_config(config_path, targets_path=targets_path, matcher_path=matcher_path, env=_env())

    assert raised.value.problems == (
        ConfigProblem(
            file_path=config_path,
            key="search.keywords",
            message="List should have at least 1 item after validation, not 0",
        ),
        ConfigProblem(file_path=targets_path, key=None, message="No such file or directory"),
        ConfigProblem(file_path=matcher_path, key="rules", message="Input should be a valid list"),
    )

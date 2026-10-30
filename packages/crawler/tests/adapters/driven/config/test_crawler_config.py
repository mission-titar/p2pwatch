from pathlib import Path

import pytest

from catalog_matching.domain.validation import parse_matcher_config, parse_targets
from p2pwatch.adapters.driven.config.crawler_config import load_config
from p2pwatch.adapters.driven.config.interpolation import interpolate_document
from p2pwatch.adapters.driven.config.yaml_loader import load_yaml
from p2pwatch.domain.crawler_config import LoadedConfig, parse_crawler_config
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
        crawler_config=parse_crawler_config(
            interpolate_document(load_yaml(config_path), env=_env())
        ),
        targets=parse_targets(load_yaml(targets_path)),
        matcher_config=parse_matcher_config(load_yaml(matcher_path)),
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
        ("['${P2PWATCH_UNSET}']", "", r"search\.keywords\[0\]"),
        # Resolved everywhere, so even a section the parse skips needs its variable.
        (
            "[keroro]",
            "download: {enabled: false, output_dir: '${P2PWATCH_UNSET}'}\n",
            r"download\.output_dir",
        ),
    ],
    ids=["keywords", "disabled-section"],
)
def test_an_unset_variable_under_any_key_is_an_invalid_config_naming_its_key_path(
    *, tmp_path: Path, keywords: str, extra: str, key_path: str
) -> None:
    config_path = _write_crawler_config(tmp_path, keywords=keywords, extra=extra)
    with pytest.raises(
        InvalidConfigError,
        match=rf"^{key_path}: environment variable 'P2PWATCH_UNSET' referenced but not set$",
    ):
        _load_with_the_shipped_policy(config_path, env=_env())


@pytest.mark.parametrize(
    ("broken_file", "text", "key", "message"),
    [
        ("crawler.yml", "search: [unclosed\n", None, "{path}: invalid YAML: "),  # a broken file
        ("crawler.yml", "search: {}\n", "search.keywords", "missing"),
        ("targets.yml", "episodes: nope\n", None, "'episodes' section: list expected"),
        ("matcher.yml", "tokens: {}\nrules: {}\n", None, "'rules' section: list expected"),
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

    assert raised.value.key == key
    assert raised.value.message.startswith(message.format(path=paths[broken_file]))

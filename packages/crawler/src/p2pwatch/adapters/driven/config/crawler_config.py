"""Reads the three config files and hands their parse to the domain (``domain/crawler_config``)."""

from collections.abc import Mapping
from pathlib import Path

from catalog_matching.domain.config import MatcherConfig
from catalog_matching.domain.models import TargetSegment
from catalog_matching.domain.validation import (
    MatchingConfigError,
    parse_matcher_config,
    parse_targets,
)
from p2pwatch.adapters.driven.config.interpolation import interpolate_document
from p2pwatch.adapters.driven.config.yaml_loader import load_yaml
from p2pwatch.domain.broken_input_error import BrokenInputError
from p2pwatch.domain.crawler_config import CrawlerConfig, LoadedConfig, parse_crawler_config
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.policy_fingerprint import policy_fingerprint


def load_config(
    config_path: Path, targets_path: Path, matcher_path: Path, env: Mapping[str, str]
) -> LoadedConfig:
    """Loads ``crawler.yml``, ``targets.yml`` and ``matcher.yml``; any of them invalid or
    broken raises ``InvalidConfigError``, which refuses the crawl.

    The fingerprint hashes the two policy files' RAW bytes, not their parse, so a
    comment-only edit still triggers one harmless re-evaluation at the next start.
    """
    try:
        crawler_config = read_crawler_config(config_path, env)
        targets = read_targets(targets_path)
        matcher_config = read_matcher_config(matcher_path)
    except BrokenInputError as error:
        raise InvalidConfigError(None, str(error)) from error
    return LoadedConfig(
        crawler_config=crawler_config,
        targets=targets,
        matcher_config=matcher_config,
        policy_fingerprint=policy_fingerprint(matcher_path.read_bytes(), targets_path.read_bytes()),
    )


def read_crawler_config(config_path: Path, env: Mapping[str, str]) -> CrawlerConfig:
    """``crawler.yml`` parsed, its ``${NAME}`` resolved from ``env``; ``InvalidConfigError`` on a
    wrong content, ``BrokenInputError`` on a file it cannot read."""
    return parse_crawler_config(interpolate_document(load_yaml(config_path), env))


def read_targets(targets_path: Path) -> tuple[TargetSegment, ...]:
    """``targets.yml`` parsed, raising as ``read_crawler_config`` does."""
    try:
        return parse_targets(load_yaml(targets_path))
    except MatchingConfigError as error:
        raise InvalidConfigError(None, str(error)) from error


def read_matcher_config(matcher_path: Path) -> MatcherConfig:
    """``matcher.yml`` parsed, raising as ``read_crawler_config`` does."""
    try:
        return parse_matcher_config(load_yaml(matcher_path))
    except MatchingConfigError as error:
        raise InvalidConfigError(None, str(error)) from error

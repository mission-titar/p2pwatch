"""Reads the three config files and hands their parse to the domain (``domain/crawler_config``)."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from p2pwatch.adapters.driven.config.interpolation import interpolate_document
from p2pwatch.adapters.driven.config.yaml_loader import load_yaml
from p2pwatch.domain.broken_input_error import BrokenInputError
from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.config_value_error import ConfigValueError
from p2pwatch.domain.crawler_config import CrawlerConfig, LoadedConfig, parse_crawler_config
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.matching.config import MatcherConfig
from p2pwatch.domain.matching.models import TargetSegment
from p2pwatch.domain.matching.validation import (
    MatchingConfigError,
    parse_matcher_config,
    parse_targets,
)
from p2pwatch.domain.policy_fingerprint import policy_fingerprint


class FileRead[T](Protocol):
    def __call__(self) -> T: ...


def load_config(
    config_path: Path, *, targets_path: Path, matcher_path: Path, env: Mapping[str, str]
) -> LoadedConfig:
    """Loads ``crawler.yml``, ``targets.yml`` and ``matcher.yml``; ``InvalidConfigError`` with
    every problem of the three files, which refuses the crawl.

    The fingerprint hashes the two policy files' RAW bytes, not their parse, so a
    comment-only edit still triggers one harmless re-evaluation at the next start.
    """
    problems: list[ConfigProblem] = []
    crawler_config = _read_into(problems, read=lambda: read_crawler_config(config_path, env=env))
    targets = _read_into(problems, read=lambda: read_targets(targets_path))
    matcher_config = _read_into(problems, read=lambda: read_matcher_config(matcher_path))
    if crawler_config is None or targets is None or matcher_config is None:
        raise InvalidConfigError(tuple(problems))
    return LoadedConfig(
        crawler_config=crawler_config,
        targets=targets,
        matcher_config=matcher_config,
        policy_fingerprint=policy_fingerprint(
            matcher_path.read_bytes(), targets_bytes=targets_path.read_bytes()
        ),
    )


def read_crawler_config(config_path: Path, *, env: Mapping[str, str]) -> CrawlerConfig:
    """``crawler.yml`` parsed, its ``${NAME}`` resolved from ``env``; ``InvalidConfigError`` with
    every unset variable and the parse's problem."""
    interpolated = interpolate_document(_document_of(config_path), env=env, file_path=config_path)
    try:
        crawler_config = parse_crawler_config(interpolated.document)
    except ConfigValueError as error:
        problem = ConfigProblem(file_path=config_path, key=error.key, message=error.message)
        raise InvalidConfigError((*interpolated.problems, problem)) from error
    if interpolated.problems:
        raise InvalidConfigError(interpolated.problems)
    return crawler_config


def read_targets(targets_path: Path) -> tuple[TargetSegment, ...]:
    """``targets.yml`` parsed; ``InvalidConfigError`` with its problem."""
    document = _document_of(targets_path)
    try:
        return parse_targets(document)
    except MatchingConfigError as error:
        raise _one_problem(targets_path, message=str(error)) from error


def read_matcher_config(matcher_path: Path) -> MatcherConfig:
    """``matcher.yml`` parsed; ``InvalidConfigError`` with its problem."""
    document = _document_of(matcher_path)
    try:
        return parse_matcher_config(document)
    except MatchingConfigError as error:
        raise _one_problem(matcher_path, message=str(error)) from error


def _read_into[T](problems: list[ConfigProblem], *, read: FileRead[T]) -> T | None:
    """``read``'s value, or ``None`` with its file's problems appended to ``problems``."""
    try:
        return read()
    except InvalidConfigError as error:
        problems.extend(error.problems)
        return None


def _document_of(file_path: Path) -> dict[str, Any]:
    """The YAML document of ``file_path``; ``InvalidConfigError`` when it cannot be read."""
    try:
        return load_yaml(file_path)
    except BrokenInputError as error:
        raise _one_problem(file_path, message=error.reason) from error


def _one_problem(file_path: Path, *, message: str) -> InvalidConfigError:
    return InvalidConfigError((ConfigProblem(file_path=file_path, key=None, message=message),))

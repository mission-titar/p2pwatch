"""Reads the three config files into the domain's objects."""

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from p2pwatch.adapters.driven.config.crawler_config_schema import crawler_config_from_document
from p2pwatch.adapters.driven.config.interpolation import interpolate_document
from p2pwatch.adapters.driven.config.matcher_config_schema import matcher_config_from_document
from p2pwatch.adapters.driven.config.targets_schema import targets_from_document
from p2pwatch.adapters.driven.config.yaml_loader import LoadedDocument, load_yaml
from p2pwatch.domain.broken_input_error import BrokenInputError
from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.crawler_config import CrawlerConfig, LoadedConfig
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.matching.config import MatcherConfig
from p2pwatch.domain.matching.models import TargetSegment
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
    every key written twice, every unset variable and the parse's problems."""
    loaded = _document_of(config_path)
    interpolated = interpolate_document(loaded.document, env=env, file_path=config_path)
    return _parsed(
        (*loaded.problems, *interpolated.problems),
        parse=lambda: crawler_config_from_document(interpolated.document, file_path=config_path),
    )


def read_targets(targets_path: Path) -> tuple[TargetSegment, ...]:
    """``targets.yml`` parsed; ``InvalidConfigError`` with every key written twice and the parse's
    problems."""
    loaded = _document_of(targets_path)
    return _parsed(
        loaded.problems,
        parse=lambda: targets_from_document(loaded.document, file_path=targets_path),
    )


def read_matcher_config(matcher_path: Path) -> MatcherConfig:
    """``matcher.yml`` parsed; ``InvalidConfigError`` with every key written twice and the parse's
    problems."""
    loaded = _document_of(matcher_path)
    return _parsed(
        loaded.problems,
        parse=lambda: matcher_config_from_document(loaded.document, file_path=matcher_path),
    )


def _parsed[T](problems: tuple[ConfigProblem, ...], *, parse: FileRead[T]) -> T:
    """``parse``'s value; ``InvalidConfigError`` with ``problems`` then the parse's, when either
    holds one."""
    try:
        value = parse()
    except InvalidConfigError as error:
        raise InvalidConfigError((*problems, *error.problems)) from error
    if problems:
        raise InvalidConfigError(problems)
    return value


def _read_into[T](problems: list[ConfigProblem], *, read: FileRead[T]) -> T | None:
    """``read``'s value, or ``None`` with its file's problems appended to ``problems``."""
    try:
        return read()
    except InvalidConfigError as error:
        problems.extend(error.problems)
        return None


def _document_of(file_path: Path) -> LoadedDocument:
    """The YAML document of ``file_path``; ``InvalidConfigError`` when it cannot be read."""
    try:
        return load_yaml(file_path)
    except BrokenInputError as error:
        raise _one_problem(file_path, message=error.reason) from error


def _one_problem(file_path: Path, *, message: str) -> InvalidConfigError:
    return InvalidConfigError((ConfigProblem(file_path=file_path, key=None, message=message),))

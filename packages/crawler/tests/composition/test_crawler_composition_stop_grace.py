"""Docker's stop grace outlasts the crawler's whole bounded stop: its deadline, then its close."""

import re
from pathlib import Path

import yaml

from p2pwatch.adapters.driven.config.crawler_config_schema import MAX_SHUTDOWN_DEADLINE_SECONDS
from p2pwatch.composition.crawler_composition import CLOSE_TIMEOUT_SECONDS

_DEPLOY = Path(__file__).resolve().parents[4] / "deploy"
_SECONDS = re.compile(r"(\d+)s")


def _grace_seconds() -> int:
    compose = yaml.safe_load((_DEPLOY / "compose.yml").read_text(encoding="utf-8"))
    grace = _SECONDS.fullmatch(compose["services"]["p2pwatch"]["stop_grace_period"])
    assert grace is not None
    return int(grace.group(1))


def test_compose_kills_the_crawler_only_past_its_shipped_deadline_and_its_close() -> None:
    crawler = yaml.safe_load((_DEPLOY / "crawler.yml").read_text(encoding="utf-8"))
    assert _grace_seconds() > crawler["shutdown_deadline_seconds"] + CLOSE_TIMEOUT_SECONDS


def test_compose_kills_the_crawler_only_past_the_longest_deadline_it_accepts_and_its_close() -> (
    None
):
    assert _grace_seconds() >= MAX_SHUTDOWN_DEADLINE_SECONDS + CLOSE_TIMEOUT_SECONDS

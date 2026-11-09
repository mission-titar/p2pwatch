"""Docker's stop grace outlasts the crawler's whole bounded stop: its deadline, then its close."""

import re
from pathlib import Path

import yaml

from p2pwatch.composition.crawler_composition import CLOSE_TIMEOUT_SECONDS

_DEPLOY = Path(__file__).resolve().parents[4] / "deploy"
_SECONDS = re.compile(r"(\d+)s")


def test_compose_kills_the_crawler_only_past_its_shipped_deadline_and_its_close() -> None:
    compose = yaml.safe_load((_DEPLOY / "compose.yml").read_text(encoding="utf-8"))
    crawler = yaml.safe_load((_DEPLOY / "crawler.yml").read_text(encoding="utf-8"))

    grace = _SECONDS.fullmatch(compose["services"]["p2pwatch"]["stop_grace_period"])

    assert grace is not None
    assert int(grace.group(1)) > crawler["shutdown_deadline_seconds"] + CLOSE_TIMEOUT_SECONDS

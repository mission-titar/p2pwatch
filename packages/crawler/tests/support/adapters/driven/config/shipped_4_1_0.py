"""4.1.0's shipped config, its two commented notifications uncommented, and its problems in 5.0."""

from pathlib import Path

_FIXTURES = Path(__file__).resolve().parents[4] / "fixtures" / "v4.1.0"

CRAWLER_PATH = _FIXTURES / "crawler.yml"
MATCHER_PATH = _FIXTURES / "matcher.yml"
# 4.1.0's targets.yml, byte for byte (the spec's appendix C: it holds no problem).
TARGETS_PATH = Path(__file__).resolve().parents[7] / "deploy" / "targets.yml"

ENV = {
    "AMULE_API_PASSWORD": "s3cr3t",
    "DISCORD_WEBHOOK_ID": "1",
    "DISCORD_WEBHOOK_TOKEN": "operations-token",
    "DISCORD_COMMUNITY_ID": "2",
    "DISCORD_COMMUNITY_TOKEN": "community-token",
}

_REMOVED = "was removed, delete it from crawler.yml"
_RENAMED_AUDIENCE = "was renamed 'audience', rename it in crawler.yml"

# Each (file, key, message), in the order validate-config and the start list them.
PROBLEMS = (
    (CRAWLER_PATH, "observability.notifications[0].tag", _RENAMED_AUDIENCE),
    (CRAWLER_PATH, "observability.notifications[1].tag", _RENAMED_AUDIENCE),
    (CRAWLER_PATH, "observability.metrics", _REMOVED),
    (CRAWLER_PATH, "webui.enabled", _REMOVED),
    (CRAWLER_PATH, "cycle_interval_seconds", _REMOVED),
    (CRAWLER_PATH, "decision_poll_interval_seconds", _REMOVED),
    (CRAWLER_PATH, "keyword_pause_max_seconds", _REMOVED),
    (CRAWLER_PATH, "keyword_pause_min_seconds", _REMOVED),
    (CRAWLER_PATH, "port_sync", _REMOVED),
    (CRAWLER_PATH, "search_poll_budget_seconds", _REMOVED),
    (CRAWLER_PATH, "search_poll_interval_seconds", _REMOVED),
    (CRAWLER_PATH, "backoff", "moved to 'search.backoff', move it in crawler.yml"),
    (
        MATCHER_PATH,
        "tokens.segment_id.regex",
        "placeholder '{segment}' was renamed '{letter}', rename it in matcher.yml",
    ),
    (MATCHER_PATH, "tokens.title_hit.min", "was renamed 'min_coverage', rename it in matcher.yml"),
)

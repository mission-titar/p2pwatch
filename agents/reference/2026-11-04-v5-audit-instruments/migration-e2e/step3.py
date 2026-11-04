"""step3.py DIR: migration-4x.md's step 3, applied to DIR/crawler.yml and DIR/matcher.yml."""

import re
import sys
from pathlib import Path

directory = Path(sys.argv[1])
crawler = directory / "crawler.yml"
text = crawler.read_text()
for key in (
    "cycle_interval_seconds", "decision_poll_interval_seconds", "search_poll_budget_seconds",
    "search_poll_interval_seconds", "keyword_pause_min_seconds", "keyword_pause_max_seconds",
):
    text = re.sub(rf"^{key}:.*\n", "", text, flags=re.MULTILINE)
text = text[: text.index("# Port-sync only works")].rstrip() + "\n"
text = text.replace("  enabled: true\n  # Resolved by", "  # Resolved by")
text = text.replace("  metrics: { enabled: true, port: 9090 }\n", "")
backoff = "backoff:\n  base_seconds: 2.0\n  cap_seconds: 300.0\n  factor: 2.0\n  jitter_ratio: 0.3\n\n"
assert backoff in text
text = text.replace(backoff, "")
text = text.replace(
    "search:\n  keywords: [keroro, titar]\n",
    "search:\n  keywords: [keroro, titar]\n  backoff:\n    base_seconds: 2.0\n    cap_seconds: 300.0\n"
    "    factor: 2.0\n    jitter_ratio: 0.3\n",
)
crawler.write_text(text.replace(" tag: ", " audience: "))
matcher = directory / "matcher.yml"
matcher.write_text(
    matcher.read_text()
    .replace('\\\\s*{segment}"', '\\\\s*{letter}"')
    .replace("{ coverage: title, min: 0.6 }", "{ coverage: title, min_coverage: 0.6 }")
)

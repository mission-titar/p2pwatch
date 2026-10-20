"""The values the crawler takes for a key ``crawler.yml`` leaves out."""

from datetime import timedelta

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_NOTIFICATION_TIMEOUT_SECONDS = 5.0
DEFAULT_NODE_PREFIX = True

DEFAULT_WEBUI_ENABLED = True
# The no-proxy case: aMule's web UI on its published port.
DEFAULT_AMULE_URL = "http://localhost:4711"
# 3 x (300 + 30): the carried role's max age at the shipped intervals (source points spec, D6).
DEFAULT_SOURCE_PERIOD_GAP = timedelta(seconds=990)

DEFAULT_DOWNLOAD_ENABLED = False
# The knobs of 2026-09-13 default rather than fail fast: a config written before them boots.
DEFAULT_MIN_FREE_BYTES = 10_737_418_240  # 10 GiB
DEFAULT_LOST_AFTER = timedelta(hours=24)  # absorbs an amuled restart or a night of downtime
DEFAULT_OUTPUT_DIR = "/downloads"  # the bind mount in deploy/compose.yml
DEFAULT_REAPPEARED_AFTER = timedelta(hours=12)  # a night off does not notify (stage 4 spec, D9)
# 5 min: enough to recognise a sharer, a tenth of the detail calls (source points spec, D3).
DEFAULT_SOURCES_INTERVAL = timedelta(minutes=5)

"""main's loader on the unmigrated and the half-migrated matcher.yml: both must be refused."""

import sys
from pathlib import Path

from p2pwatch.adapters.driven.config.crawler_config import read_matcher_config
from p2pwatch.domain.invalid_config import InvalidConfigError

scratch = Path(sys.argv[1])
original = (scratch / "cfg4" / "matcher.yml").read_text()
half = scratch / "half_migrated_matcher.yml"
half.write_text(original.replace("min: 0.6", "min_coverage: 0.6"))
for path in (scratch / "cfg4" / "matcher.yml", half):
    try:
        read_matcher_config(path)
        print(f"{path.name}: ACCEPTED")
    except InvalidConfigError as error:
        print(f"{path.name}: refused: {error}")

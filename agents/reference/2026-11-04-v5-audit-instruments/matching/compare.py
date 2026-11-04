"""Compares two evaluate.py outputs: decisions per file, explanations per (file, target).

argv: left dir, right dir. Exit 1 when anything differs.
"""

import json
import sys
from pathlib import Path

left, right = Path(sys.argv[1]), Path(sys.argv[2])
status = 0
for name in ("decisions.json", "explanations.json"):
    a = json.loads((left / name).read_text())
    b = json.loads((right / name).read_text())
    keys = sorted(set(a) | set(b))
    differing = [k for k in keys if a.get(k) != b.get(k)]
    print(f"{name}: keys={len(keys)} differing={len(differing)}")
    for k in differing[:15]:
        print(f"  {k}\n    left ={a.get(k)}\n    right={b.get(k)}")
    if differing:
        status = 1
sys.exit(status)

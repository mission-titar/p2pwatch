"""One version's engine over inputs.json: its decisions and its per-target explanations.

argv: v4|main, config dir, inputs.json, output dir.
"""

import json
import sys
from dataclasses import replace
from pathlib import Path

version, cfg, inputs_path, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])

if version == "v4":
    from catalog_matching.engine import MatchingEngine
    from catalog_matching.validation import parse_matcher_config, parse_targets
    from mulewatch.adapters.config.yaml_loader import load_yaml
    from mulewatch.domain.observation import candidate_from_fields

    targets = parse_targets(load_yaml(cfg / "targets.yml"))
    engine = MatchingEngine(parse_matcher_config(load_yaml(cfg / "matcher.yml")), targets)

    def build(row: dict) -> object:
        return candidate_from_fields(
            row["filename"], row["size_bytes"], row["duration_seconds"], row["bitrate_kbps"]
        )

    evaluate = engine.evaluate_all

    def explain(candidates: list, target_id: str) -> object:
        return engine.explain(candidates, target_id)
else:
    from catalog_matching.domain.engine import MatchingEngine
    from p2pwatch.adapters.driven.config.crawler_config import read_matcher_config, read_targets
    from p2pwatch.domain.observation import candidate_from_fields

    targets = read_targets(cfg / "targets.yml")
    engine = MatchingEngine(
        read_matcher_config(cfg / "matcher.yml"), targets=targets, max_filename_length=4096
    )

    def build(row: dict) -> object:
        return candidate_from_fields(
            row["filename"],
            size_bytes=row["size_bytes"],
            duration_seconds=row["duration_seconds"],
            bitrate_kbps=row["bitrate_kbps"],
        )

    evaluate = engine.evaluate_file

    def explain(candidates: list, target_id: str) -> object:
        return engine.explain(candidates, target_id=target_id)


decisions = {}
explanations = {}
for row in json.loads(inputs_path.read_text()):
    base = build(row)
    candidates = [replace(base, filename=name) for name in row["known_filenames"]]
    decisions[row["hash"]] = sorted(
        [d.target_id, d.rule_name, str(d.tier)] for d in evaluate(candidates)
    )
    for target in targets:
        e = explain(candidates, target.target_id)
        coverage = [[name, round(value, 9)] for name, value in e.coverage_values if value > 0]
        if e.rules_fired or e.tokens_matched or e.vetoes_fired or coverage:
            explanations[f"{row['hash']}|{e.target_id}"] = [
                list(e.rules_fired),
                list(e.tokens_matched),
                coverage,
                list(e.vetoes_fired),
            ]
out.mkdir(exist_ok=True)
(out / "decisions.json").write_text(json.dumps(decisions, ensure_ascii=False))
(out / "explanations.json").write_text(json.dumps(explanations, ensure_ascii=False))
print(
    f"{version}: files={len(decisions)} targets={len(targets)} "
    f"decisions={sum(len(v) for v in decisions.values())} explanations={len(explanations)}"
)

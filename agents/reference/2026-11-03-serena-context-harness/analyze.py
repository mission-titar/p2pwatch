"""Per run: cost, turns, time, canary, Serena calls, hook blocks, red checks, then the fix loop."""

import collections
import json
import re
import sys
from pathlib import Path

S = Path(__file__).parent


def lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.startswith("{")]


def result_text(block: dict) -> str:
    content = block["content"]
    return content if isinstance(content, str) else " ".join(b.get("text", "") for b in content)


def session_stats(entries: list[dict]) -> dict:
    result = next((line for line in reversed(entries) if line.get("type") == "result"), {})
    tools: collections.Counter[str] = collections.Counter()
    blocks = 0
    for line in entries:
        if line.get("type") == "assistant":
            for block in line["message"].get("content", []):
                if block.get("type") == "tool_use":
                    tools[block["name"].replace("mcp__serena__", "serena:")] += 1
        content = line.get("message", {}).get("content") if line.get("type") == "user" else None
        for block in content if isinstance(content, list) else []:
            if block.get("type") == "tool_result":
                blocks += "Too many consecutive" in result_text(block)
    serena_tools = {t: n for t, n in tools.items() if t.startswith("serena:")}
    return {
        "cost": result.get("total_cost_usd", 0),
        "turns": result.get("num_turns") or 0,
        "canary": "ORNITHORYNQUE-8" in (result.get("result") or ""),
        "serena": sum(serena_tools.values()),
        "serena_tools": serena_tools,
        "reads": tools["Read"] + tools["Grep"] + tools["Glob"],
        "edits": tools["Edit"] + tools["Write"],
        "blocks": blocks,
    }


def gate_calls(entries: list[dict]) -> list[str]:
    """One `<task>:<verdict>` per poe call of the session, in order."""
    uses: dict[str, str] = {}
    calls: list[str] = []
    for line in entries:
        if line.get("type") == "assistant":
            for block in line["message"].get("content", []):
                if block.get("type") == "tool_use" and "poe" in block["input"].get("command", ""):
                    uses[block["id"]] = block["input"]["command"]
        content = line.get("message", {}).get("content") if line.get("type") == "user" else None
        for block in content if isinstance(content, list) else []:
            if block.get("type") == "tool_result" and block["tool_use_id"] in uses:
                text = result_text(block)
                failed = re.search(r"Subtasks? '([^\n]+?)' returned non-zero", text) or re.search(
                    r"failed subtask '([^']+)'", text
                )
                command = uses[block["tool_use_id"]].split("poe ", 1)[-1].split()[0]
                if failed:
                    verdict = failed.group(1)
                elif "GATE GREEN" in text or not block.get("is_error"):
                    verdict = "green"
                else:
                    verdict = "error"
                calls.append(f"{command}:{verdict}")
    return calls


def seconds(out: Path, *, start: str, end: str) -> int:
    if not (out / end).exists():
        return 0
    return int((out / end).read_text()) - int((out / start).read_text())


def red_checks(summary: Path) -> list[str]:
    if not summary.exists():
        return ["no gate"]
    return [line.split()[0] for line in summary.read_text().splitlines() if not line.endswith(" 0")]


def main() -> None:
    arm = sys.argv[1]
    total: collections.Counter[str] = collections.Counter()
    for out in sorted((S / "out").glob(f"{arm}-*")):
        run = out.name.rsplit("-", 1)[0]
        first = session_stats(lines(out / "session.jsonl"))
        fix = session_stats(lines(out / "fix.jsonl"))
        run_seconds = seconds(out, start="start", end="end")
        fix_seconds = seconds(out, start="fix.start", end="fix.end")
        print(
            f"== {run}: ${first['cost']:.2f} turns={first['turns']} {run_seconds}s"
            f" canary={first['canary']} serena={first['serena']} reads={first['reads']}"
            f" edits={first['edits']} blocks={first['blocks']}"
        )
        print(f"   serena tools: {first['serena_tools']}")
        print(f"   gate red: {red_checks(S / 'gate' / run / 'summary')}")
        if (out / "fix.jsonl").exists():
            print(
                f"   fix: ${fix['cost']:.2f} turns={fix['turns']} {fix_seconds}s"
                f" serena={fix['serena']} blocks={fix['blocks']}"
                f" gate calls={gate_calls(lines(out / 'fix.jsonl'))}"
                f" final red={red_checks(S / 'gate' / f'{run}-fixed' / 'summary')}"
            )
        total["runs"] += 1
        total["cost"] += first["cost"] + fix["cost"]
        total["turns"] += first["turns"] + fix["turns"]
        total["seconds"] += run_seconds + fix_seconds
        total["serena"] += first["serena"] + fix["serena"]
        total["blocks"] += first["blocks"] + fix["blocks"]
        total["red_first"] += red_checks(S / "gate" / run / "summary") not in ([], ["no gate"])
    print(
        f"\n{arm}: runs={total['runs']} cost to green=${total['cost']:.2f} turns={total['turns']}"
        f" seconds={total['seconds']} serena calls={total['serena']} hook blocks={total['blocks']}"
        f" runs red at first gate={total['red_first']}"
    )


main()

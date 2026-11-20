"""Measure Qwen on an explicitly dated XAUUSD snapshot using the local Ollama API."""

import argparse
import json
from dataclasses import replace
from pathlib import Path

from replay_gold_tool_contract import add_evidence_arguments, load_tools

from goldintel.agents.ollama import replay
from goldintel.agents.tools import TOOL_DESCRIPTIONS, utc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_evidence_arguments(parser)
    parser.add_argument("--expiry-as-of", type=utc)
    parser.add_argument("--port", type=int, default=11435)
    parser.add_argument("--rounds", type=int, choices=range(1, 6), default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    gold = load_tools(args)
    expired = replace(gold, decision_time_utc=args.expiry_as_of) if args.expiry_as_of else None
    if expired is not None and "snapshot_expired" not in expired.call(
            "get_risk_status", {"symbol": "XAUUSD"})["blockers"]:
        parser.error("--expiry-as-of must select a time after the snapshot expires")
    reports = [replay(args.port, gold, name) for _ in range(args.rounds)
               for name in TOOL_DESCRIPTIONS if name != "get_risk_status"]
    if expired is not None:
        reports.extend(replay(args.port, expired, name) for name in (
            "get_gold_market_snapshot", "get_gold_forecasts", "get_macro_events"))
    passed = sum(report["status"] == "verified_replay" for report in reports)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump({"scope": "historical replay", "cases_passed": passed,
                   "cases_total": len(reports), "reports": reports}, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(f"Verified {passed}/{len(reports)} model replays")
    return int(passed != len(reports))


if __name__ == "__main__":
    raise SystemExit(main())

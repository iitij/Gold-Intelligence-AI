"""Run a local council evidence rehearsal with a deterministic risk decision."""

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from replay_gold_tool_contract import add_evidence_arguments, load_tools

from goldintel.agents.ollama import replay
from goldintel.research.holdout import assert_no_sealed_overlap

REGISTRY = Path(__file__).resolve().parents[1] / "planning/holdout_registry.json"
ROLES = (
    ("technical", "get_gold_market_snapshot"),
    ("macro", "get_macro_events"),
    ("bull_case_evidence", "get_gold_forecasts"),
    ("bear_case_countercheck", "get_strategy_spec"),
)


def council(port, gold):
    now = datetime.now(timezone.utc)
    decision = gold.decision_time_utc
    if decision > now:
        raise ValueError("Council rehearsal requires an elapsed evidence time")
    assert_no_sealed_overlap(REGISTRY, now=now, start=decision, end=decision + timedelta(microseconds=1))
    arguments = {"symbol": "XAUUSD"}
    risk = gold.call("get_risk_status", arguments)
    roles = {}
    for role, tool in ROLES:
        tool_args = {**arguments, "strategy_id": "STR-003"} if tool == "get_strategy_spec" else arguments
        evidence = gold.call(tool, tool_args)
        encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        result = replay(port, gold, tool)
        roles[role] = {"evidence_tool": tool, "evidence_sha256": hashlib.sha256(encoded).hexdigest(),
                       "evidence_status": evidence["status"], "replay": result}
    roles["news"] = {"status": "disabled", "reason": "No verified news-source adapter", "tool_calls": []}
    roles["risk_reviewer"] = {"status": "deterministic_policy", "evidence_tool": "get_risk_status", "result": risk}
    verified = sum(roles[role]["replay"]["status"] == "verified_replay" for role, _ in ROLES)
    return {"schema_version": 1, "scope": "historical council evidence rehearsal",
            "snapshot_id": risk["snapshot_id"], "decision_time_utc": risk["decision_time_utc"],
            "model_roles_verified": verified, "model_roles_expected": len(ROLES),
            "advisory": "NO_TRADE", "execution_ready": False, "roles": roles}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_evidence_arguments(parser)
    parser.add_argument("--port", type=int, default=11435)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = council(args.port, load_tools(args))
    result["input_evidence"] = {"market_snapshot_id": args.snapshot_id, "macro_snapshot_id": args.macro_snapshot_id,
                                "forecast_file_sha256": args.forecast_sha256,
                                "calendar_file_sha256": args.calendar_sha256}
    with args.output.open("x") as output:
        output.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(f"Verified {result['model_roles_verified']}/{result['model_roles_expected']} model roles; NO_TRADE")
    return int(result["model_roles_verified"] != result["model_roles_expected"])


if __name__ == "__main__":
    raise SystemExit(main())

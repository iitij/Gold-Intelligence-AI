"""Read-only, fail-closed evidence gates. NEVER enables execution or training.

Run: python scripts/preflight.py status
     python scripts/preflight.py check G0
     python scripts/preflight.py check training
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "planning/preflight_gates.json"

MANDATORY = {
    "G0": {"provenance", "dependency_lock", "sbom_security_triage",
           "github_maintainer_review_policy"},
    "G1": {"broker_symbol_contract", "broker_timezone_dst", "bid_ask_tick_quality",
           "raw_data_rights_and_hashes"},
    "G2": {"baselines", "walkforward_no_leakage", "locked_holdout",
           "model_calibration_and_trial_ledger"},
    "G3": {"event_replay_bid_ask", "commission_swap_spread_latency",
           "unknown_fills_and_stress"},
    "G4": {"secrets_and_access_control", "broker_loss_margins_reservations",
           "no_llm_trade_permissions", "idempotency_reconciliation_kill_switch"},
    "G5": {"mt5_demo_forward_testing", "regimes_and_broker_cost_records",
           "restore_recovery_drills"},
    "G6": {"independent_audit", "legal_and_broker_terms",
           "owner_explicit_authorization", "deployment_and_rollback_proof"},
}
GOALS = {
    "training": ("G0", "G1"),
    "research-evaluation": ("G0", "G1", "G2", "G3"),
    "demo": ("G0", "G1", "G2", "G3", "G4"),
    "production": tuple(MANDATORY),
}


class GateError(ValueError):
    """Malformed or unsupported readiness manifest."""


def read_gates(path: Path = MANIFEST) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("policy") != (
        "FAIL_CLOSED_PAPER_ONLY_HUMAN_REVIEW_REQUIRED"
    ):
        raise GateError("Unexpected evidence policy or manifest schema")
    gates = data.get("gates")
    if not isinstance(gates, list) or len(gates) != len(MANDATORY):
        raise GateError("Wrong gate inventory")
    ids = [g.get("id") for g in gates]
    if len(ids) != len(set(ids)) or set(ids) != set(MANDATORY):
        raise GateError("Missing/duplicated gate")
    for g in gates:
        if g.get("status") not in {"blocked", "in_review", "accepted"}:
            raise GateError("Unknown gate status")
        rows = g.get("requirements")
        if not isinstance(rows, list) or len(rows) != len(MANDATORY[g["id"]]):
            raise GateError("Incomplete gate requirements")
        keys = [r.get("id") for r in rows]
        if len(keys) != len(set(keys)) or set(keys) != MANDATORY[g["id"]]:
            raise GateError("Missing/duplicated mandatory evidence")
        for item in rows:
            if not isinstance(item.get("verified"), bool):
                raise GateError("Verification must be a boolean")
            refs = item.get("evidence")
            if not isinstance(refs, list) or not all(
                isinstance(ref, str) and ref.strip() for ref in refs
            ):
                raise GateError("Evidence must be a list of nonempty references")
            if item["verified"] and not refs:
                raise GateError("Verified criterion without evidence")
    return data


def accepted_gates(data: dict) -> set[str]:
    """Manual attestations and source references; never a production permit."""
    return {
        g["id"] for g in data["gates"]
        if g["status"] == "accepted" and all(
            r["verified"] and r["evidence"] for r in g["requirements"]
        )
    }


def check_goal(data: dict, goal: str) -> tuple[bool, list[str]]:
    required = GOALS.get(goal, (goal,))
    if any(g not in MANDATORY for g in required):
        raise GateError("Unknown goal or gate")
    accepted = accepted_gates(data)
    missing = [g for g in required if g not in accepted]
    return not missing, missing


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "check"))
    parser.add_argument("goal", nargs="?")
    args = parser.parse_args()
    data = read_gates()
    if args.action == "status":
        good = accepted_gates(data)
        for item in data["gates"]:
            total = len(item["requirements"])
            supported = sum(1 for r in item["requirements"] if
                            r["verified"] and r["evidence"])
            print(f'{item["id"]}: {item["status"]} ({supported}/{total} evidence) '
                  f'accepted={item["id"] in good}')
        return
    if not args.goal:
        parser.error("check requires G0..G6 or training/research-evaluation/demo/production")
    try:
        passed, missing = check_goal(data, args.goal)
    except GateError as exc:
        parser.exit(2, f"BLOCKED: {exc}\n")
    if not passed:
        parser.exit(2, "BLOCKED: insufficient evidence for " +
                    args.goal + ": " + ", ".join(missing) + "\n")
    print("ATTESTED:", args.goal,
          "(manual evidence record only; NOT an execution authorization)")


if __name__ == "__main__":
    main()

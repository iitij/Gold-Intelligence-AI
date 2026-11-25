"""Collect provenance-bound Headway holdout blockers without opening prices."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from goldintel.research.holdout import read_protocol

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "planning/prospective_holdout_20261118.json"


def read(path):
    raw = path.read_bytes()
    record = json.loads(raw)
    if record["schema_version"] != 1:
        raise ValueError("Unsupported audit schema")
    return record, hashlib.sha256(raw).hexdigest()


def audit(reconciled, clock, sessions, costs, runtime, now):
    protocol_hash = PROTOCOL.with_suffix(".sha256").read_text().strip()
    protocol = read_protocol(PROTOCOL, protocol_hash)
    first, end = protocol["start_utc"], protocol["end_exclusive_utc"]
    quotes, quote_hash = read(reconciled)
    clock_report, clock_hash = read(clock)
    sessions_report, sessions_hash = read(sessions)
    cost_report, cost_hash = read(costs)
    runtime_report, runtime_hash = read(runtime)
    if (quotes["server"], quotes["symbol"]) != (protocol["server"], protocol["symbol"]):
        raise ValueError("Reconciliation belongs to a different symbol or server")
    if any(item["reconciliation_sha256"] != quote_hash for item in (clock_report, sessions_report)):
        raise ValueError("Quote, clock and session audits must refer to the exact same reconciliation")
    if any(item["protocol_sha256"] != protocol_hash for item in (cost_report, runtime_report)):
        raise ValueError("Audit protocol fingerprint differs")
    if (cost_report["window_start_utc"], cost_report["window_end_exclusive_utc"]) != (first, end):
        raise ValueError("Cost evidence range differs from the registered window")
    expected_cases = {(model, horizon) for model in protocol["secondary"]["models"]
                      for horizon in protocol["secondary"]["horizons_M15"]}
    cases = runtime_report["synthetic_load_and_calibration_cases"]
    scorer = ROOT / "scripts/score_registered_classifiers.py"
    runtime_bound = (runtime_report["frozen_files_verified"] == len(protocol["frozen_files"])
                     and runtime_report["historical_priors_recomputed"] == len(protocol["secondary"]["horizons_M15"])
                     and len(cases) == len(expected_cases)
                     and {(item["model"], item["horizon_m15"]) for item in cases} == expected_cases
                     and runtime_report["holdout_inputs_opened"] is False
                     and runtime_report["holdout_scored"] is False
                     and runtime_report["scorer_sha256"] == hashlib.sha256(scorer.read_bytes()).hexdigest())
    released = now >= datetime.fromisoformat(end)
    blockers = ["full_period_utc_mapping_requires_review", "utc_boundary_context_not_verified",
                "market_coverage_requires_review", "cost_terms_require_review"]
    if not released:
        blockers.append("holdout_sealed")
    if quotes["all_requests_reconciled"] is not True:
        blockers.append("native_acquisition_unresolved")
    if sessions_report["has_unresolved_market_windows"] is not False:
        blockers.append("quote_session_exceptions_unresolved")
    if cost_report["constant_commission_candidate"] is None:
        blockers.append("no_documented_constant_commission_candidate")
    if not runtime_bound:
        blockers.append("frozen_runtime_audit_incomplete_or_stale")
    return {"schema_version": 1, "protocol_sha256": protocol_hash, "checked_at_utc": now.isoformat(),
            "registered_start_utc": first, "registered_end_exclusive_utc": end, "release_boundary_passed": released,
            "source_sha256": {"native_reconciliation": quote_hash, "clock": clock_hash,
                              "quote_sessions": sessions_hash, "commission": cost_hash, "runtime": runtime_hash},
            "progress": {"native_request_status_counts": quotes["window_status_counts"],
                         "native_end_exclusive": quotes["windows"][-1]["native_end_exclusive"],
                         "direct_clock_matches": clock_report["distinct_matched_native_timestamps"],
                         "quote_session_classifications": sessions_report["classification_counts"],
                         "commission_intervals_with_bound_evidence": cost_report["intervals_with_bound_evidence"],
                         "frozen_runtime_evidence_matches": runtime_bound},
            "blockers": blockers, "holdout_scored": False, "evaluation_attested": False,
            "approved_for_trading": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("reconciled", "clock", "sessions", "costs", "runtime", "output"):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    report = audit(args.reconciled, args.clock, args.sessions, args.costs, args.runtime,
                   datetime.now(timezone.utc))
    with args.output.open("x") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print("; ".join(report["blockers"]))


if __name__ == "__main__":
    main()

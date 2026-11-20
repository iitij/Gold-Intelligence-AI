"""Reconcile separate, overlapping Headway export attempts without scoring prices."""

import argparse
import hashlib
import json
from collections import Counter
from datetime import timedelta
from pathlib import Path

from audit_headway_tick_batches import audit_batches, native_bound

STEP = timedelta(minutes=2)


def reconcile(start, end, attempts):
    if not start < end or end - start > timedelta(days=60):
        raise ValueError("Use an increasing native interval of at most 60 days")
    windows = {}
    cursor = start
    while cursor < end:
        stop = min(cursor + STEP, end)
        windows[(cursor, stop)] = []
        cursor = stop
    seen = set()
    sources = []
    for root, lower, upper in attempts:
        if root.resolve() in seen:
            raise ValueError("Attempt directories must be distinct")
        seen.add(root.resolve())
        report = audit_batches(root / "batches", root / "export.log", lower, upper)
        source_id = len(sources)
        sources.append({"attempt": str(root), "export_log_sha256": report["export_log_sha256"],
                        "request_status_counts": report["window_status_counts"]})
        for row in report["windows"]:
            key = tuple(native_bound(row[k]) for k in (
                "requested_native_start", "requested_native_end_exclusive",
            ))
            if key not in windows:
                raise ValueError("Attempt request does not align with the target windows")
            windows[key].append({"attempt_index": source_id, **row})

    outcomes = []
    for (lower, upper), observations in windows.items():
        reported = [row for row in observations if row["status"] in {"saved_verified", "reported_empty"}]
        signatures = {(row["status"], row.get("sha256")) for row in reported}
        # A contradictory unreceipted file is still a quality issue. Preserve it
        # for review and never replace a receipted export with it.
        suspect = [row for row in observations if row["status"] == "file_without_receipt"]
        logged_counts = ({row.get("rows", 0) for row in reported}
                         | {row["logged_rows"] for row in observations
                            if row["status"] == "missing_reported_file"})
        contradicts_receipt = signatures and any(
            ("saved_verified", row["sha256"]) not in signatures for row in suspect
        )
        if len(signatures) > 1 or len(logged_counts) > 1 or contradicts_receipt:
            status = "conflicting_observations"
        elif signatures:
            status = reported[0]["status"]
        else:
            status = "unresolved"
        outcomes.append({"native_start": lower.isoformat(), "native_end_exclusive": upper.isoformat(),
                         "status": status, "observations": observations})
    counts = Counter(row["status"] for row in outcomes)
    accounted = counts["saved_verified"] + counts["reported_empty"]
    return {
        "schema_version": 1, "server": "Headway-Demo", "symbol": "XAUUSD",
        "attempts": sources, "windows": outcomes, "window_status_counts": dict(counts),
        "all_requests_reconciled": accounted == len(windows),
        "utc_mapping_verified": False, "market_coverage_verified": False,
        "holdout_data_complete": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--start", type=native_bound, required=True)
    parser.add_argument("--end", type=native_bound, required=True)
    parser.add_argument("--attempt", action="append", nargs=3, required=True,
                        metavar=("DIRECTORY", "NATIVE_START", "NATIVE_END"))
    args = parser.parse_args()
    attempts = [(Path(root), native_bound(lower), native_bound(upper))
                for root, lower, upper in args.attempt]
    report = reconcile(args.start, args.end, attempts)
    raw = (json.dumps(report, indent=2, allow_nan=False) + "\n").encode()
    with args.output.open("xb") as stream:
        stream.write(raw)
    print(f"{report['window_status_counts']}; report SHA-256: {hashlib.sha256(raw).hexdigest()}")
    if not report["all_requests_reconciled"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

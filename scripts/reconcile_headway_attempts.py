"""Reconcile separate, overlapping Headway export attempts without scoring prices."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path

from audit_headway_tick_batches import audit_batches, native_bound
from collect_closed_headway_batches import verify_closed_request

STEP = timedelta(minutes=2)


def reconcile(start, end, attempts, *, guarded=None):
    guarded = guarded or {}
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
        if str(root) in guarded:
            digest, report = guarded[str(root)]
        else:
            digest = None
            report = audit_batches(root / "batches", root / "export.log", lower, upper)
        source_id = len(sources)
        sources.append({"attempt": str(root), "export_log_sha256": report["export_log_sha256"],
                        "request_status_counts": report["window_status_counts"]})
        if digest is not None:
            sources[-1]["closed_request_sha256"] = digest
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


def previous_attempts(previous, anchors):
    """Recover the exact attempt order, requiring old guard evidence by digest."""
    windows = defaultdict(list)
    for window in previous["windows"]:
        for row in window["observations"]:
            windows[row["attempt_index"]].append(row)
    receipts = {hashlib.sha256(p.read_bytes()).hexdigest(): p for p in anchors}
    attempts, guarded = [], {}
    for i, source in enumerate(previous["attempts"]):
        root = Path(source["attempt"])
        rows = windows[i]
        if not rows:
            raise ValueError("Previous attempt has no requests")
        start = min(native_bound(row["requested_native_start"]) for row in rows)
        end = max(native_bound(row["requested_native_end_exclusive"]) for row in rows)
        if "closed_request_sha256" in source:
            digest = json.loads((root / "closed-request.json").read_bytes())["session_receipt_sha256"]
            if digest not in receipts:
                raise ValueError("Supply the original clock receipt for every previous guarded attempt")
            lo, hi, closed_hash, audit = verify_closed_request(root, receipts[digest])
            if (lo, hi, closed_hash) != (start, end, source["closed_request_sha256"]):
                raise ValueError("Previous guarded attempt receipts or bounds changed")
            guarded[str(root)] = (closed_hash, audit)
        attempts.append((root, start, end))
    return attempts, guarded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--start", type=native_bound, required=True)
    parser.add_argument("--end", type=native_bound, required=True)
    parser.add_argument("--attempt", action="append", nargs=3, default=[],
                        metavar=("DIRECTORY", "NATIVE_START", "NATIVE_END"))
    parser.add_argument("--guarded-attempt", action="append", nargs=2, default=[],
                        metavar=("DIRECTORY", "CLOCK_RECEIPT"))
    parser.add_argument("--previous", nargs=2, metavar=("REPORT", "SHA256"))
    parser.add_argument("--previous-clock-receipt", type=Path, action="append", default=[])
    args = parser.parse_args()
    if not (args.attempt or args.guarded_attempt):
        parser.error("Supply at least one attempt")
    attempts, guarded = [], {}
    previous = None
    if args.previous:
        raw = Path(args.previous[0]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != args.previous[1]:
            parser.error("Previous report fingerprint differs")
        previous = json.loads(raw)
        if ((previous["schema_version"], previous["server"], previous["symbol"]) != (1, "Headway-Demo", "XAUUSD")
                or previous["all_requests_reconciled"] is not True):
            parser.error("Only a fully accounted Headway-Demo XAUUSD report can be extended")
        old_start = native_bound(previous["windows"][0]["native_start"])
        old_end = native_bound(previous["windows"][-1]["native_end_exclusive"])
        if args.start != old_start or args.end <= old_end:
            parser.error("Keep the original start and provide a later end")
        if args.attempt:
            parser.error("Extend existing reports with guarded attempts only")
        attempts, guarded = previous_attempts(previous, args.previous_clock_receipt)
    elif args.previous_clock_receipt:
        parser.error("Previous clock receipts require --previous")
    attempts.extend((Path(root), native_bound(lower), native_bound(upper))
                    for root, lower, upper in args.attempt)
    for directory, anchor in args.guarded_attempt:
        root = Path(directory)
        start, end, digest, audit = verify_closed_request(root, Path(anchor))
        if previous is not None and start < old_end:
            parser.error("New attempt overlaps the previous report")
        attempts.append((root, start, end))
        guarded[str(root)] = (digest, audit)
    report = reconcile(args.start, args.end, attempts, guarded=guarded)
    if previous is not None:
        for field in ("attempts", "windows"):
            if report[field][:len(previous[field])] != previous[field]:
                raise ValueError(f"Previous {field} changed on re-audit")
        report["previous_report_sha256"] = args.previous[1]
    raw = (json.dumps(report, indent=2, allow_nan=False) + "\n").encode()
    with args.output.open("xb") as stream:
        stream.write(raw)
    print(f"{report['window_status_counts']}; report SHA-256: {hashlib.sha256(raw).hexdigest()}")
    if not report["all_requests_reconciled"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

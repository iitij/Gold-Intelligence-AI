"""Classify reconciled quote request windows against separately supplied session evidence."""

import argparse
import hashlib
import json
from bisect import bisect_right
from collections import Counter
from datetime import timedelta
from pathlib import Path

from audit_headway_tick_batches import native_bound

STATES = ("quote_open", "quote_closed")


def load_sessions(manifest, root, first, last):
    if ((manifest["schema_version"], manifest["server"], manifest["symbol"], manifest["kind"])
            != (1, "Headway-Demo", "XAUUSD", "quote_session_evidence")):
        raise ValueError("Expected date-specific Headway-Demo XAUUSD quote-session evidence")
    segments = []
    digest_by_path = {}
    for entry in manifest["intervals"]:
        lo, hi = (native_bound(entry[key]) for key in ("native_start", "native_end_exclusive"))
        if not first <= lo < hi <= last or entry["state"] not in STATES:
            raise ValueError("Session evidence falls outside the request range or lacks a quote state")
        source = entry["evidence"]
        rel = Path(source["path"])
        source_path = (root / rel).resolve()
        if rel.is_absolute() or not source_path.is_relative_to(root) or not source_path.is_file():
            raise ValueError("Session evidence must be a local file beneath the manifest")
        if source_path not in digest_by_path:
            digest_by_path[source_path] = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if digest_by_path[source_path] != source["sha256"]:
            raise ValueError("Session evidence fingerprint differs")
        segments.append((lo, hi, entry["state"]))
    segments.sort()
    if any(prior[1] > later[0] for prior, later in zip(segments, segments[1:])):
        raise ValueError("Session evidence intervals overlap")
    return segments


def classify(reconciliation, manifest, root):
    if (reconciliation["schema_version"], reconciliation["server"], reconciliation["symbol"]) != (
            1, "Headway-Demo", "XAUUSD"):
        raise ValueError("Unexpected reconciliation scope")
    windows = reconciliation["windows"]
    if not windows:
        raise ValueError("No native request windows")
    first = native_bound(windows[0]["native_start"])
    last = native_bound(windows[-1]["native_end_exclusive"])
    segments = load_sessions(manifest, root, first, last)
    segment_end = [item[1] for item in segments]
    summary = Counter()
    exceptions = []
    cursor = first
    for window in windows:
        lo, hi = (native_bound(window[key]) for key in ("native_start", "native_end_exclusive"))
        if lo != cursor or not timedelta() < hi - lo <= timedelta(minutes=2):
            raise ValueError("Expected contiguous request windows of at most two minutes")
        cursor = hi
        clock = Counter()
        for i in range(bisect_right(segment_end, lo), len(segments)):
            a, b, state = segments[i]
            if a >= hi:
                break
            clock[state] += (min(hi, b) - max(lo, a)) // timedelta(seconds=1)
        window_seconds = (hi - lo) // timedelta(seconds=1)
        unknown = window_seconds - sum(clock.values())
        if window["status"] == "reported_empty":
            if clock["quote_closed"] == window_seconds:
                label = "empty_with_full_closed_evidence"
            elif clock["quote_open"]:
                label = "empty_overlaps_documented_open"
            else:
                label = "empty_without_full_closed_evidence"
        elif window["status"] == "saved_verified":
            label = "saved_conflicts_with_full_closed_evidence" if clock["quote_closed"] == window_seconds else "saved"
        else:
            label = "request_unresolved"
        summary[label] += 1
        if label != "saved":
            exceptions.append({"native_start": lo.isoformat(), "native_end_exclusive": hi.isoformat(),
                               "classification": label, "quote_open_seconds": clock["quote_open"],
                               "quote_closed_seconds": clock["quote_closed"], "unclassified_seconds": unknown})
    return {"classification_counts": dict(summary), "windows_review": exceptions,
            "has_unresolved_market_windows": any(count for label, count in summary.items()
                                                  if label not in {"saved", "empty_with_full_closed_evidence"}),
            "evidence_requires_substantive_review": True,
            "market_coverage_verified": False, "utc_mapping_verified": False, "holdout_scored": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reconciliation", type=Path)
    parser.add_argument("sha256")
    parser.add_argument("quote_sessions", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    raw = args.reconciliation.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.sha256:
        raise ValueError("Reconciliation fingerprint differs")
    session_bytes = args.quote_sessions.read_bytes()
    result = classify(json.loads(raw), json.loads(session_bytes), args.quote_sessions.resolve().parent)
    with args.output.open("x") as output:
        output.write(json.dumps({"schema_version": 1, "reconciliation_sha256": args.sha256,
                                 "quote_sessions_sha256": hashlib.sha256(session_bytes).hexdigest(), **result},
                                indent=2) + "\n")
    print(result["classification_counts"])
    return 2 if result["has_unresolved_market_windows"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

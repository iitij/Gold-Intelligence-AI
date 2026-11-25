"""Audit whether raw Headway quotes continue across a scheduled native-time boundary."""

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from datetime import timedelta
from pathlib import Path

if __package__:
    from .audit_headway_tick_batches import BATCH_NAME, EPOCH, native_bound
else:
    from audit_headway_tick_batches import BATCH_NAME, EPOCH, native_bound

RADIUS = timedelta(minutes=12)
STEP = timedelta(minutes=2)
MILLISECOND = timedelta(milliseconds=1)


def probe(reconciliation, boundary):
    raw = reconciliation.read_bytes()
    report = json.loads(raw)
    if (report["schema_version"], report["server"], report["symbol"]) != (1, "Headway-Demo", "XAUUSD"):
        raise ValueError("Expected Headway-Demo XAUUSD reconciliation")
    windows = {}
    for window in report["windows"]:
        start, end = (native_bound(window[k]) for k in ("native_start", "native_end_exclusive"))
        if (start, end) in windows:
            raise ValueError("Duplicate reconciliation window")
        windows[start, end] = window
    start = boundary - RADIUS
    start -= timedelta(minutes=start.minute % 2)
    stop = boundary + RADIUS
    if stop.minute % 2:
        stop += timedelta(minutes=1)
    bound_ms = (boundary - EPOCH) // MILLISECOND
    counts = Counter()
    ticks = []
    selected = []
    while start < stop:
        end = start + STEP
        window = windows.get((start, end))
        status = window["status"] if window else "missing_from_report"
        counts[status] += 1
        selected.append({"start_native": start.isoformat(), "end_native_exclusive": end.isoformat(),
                         "status": status})
        if status == "saved_verified":
            row = next(o for o in window["observations"] if o["status"] == status)
            if not BATCH_NAME.fullmatch(row["file"]):
                raise ValueError("Unexpected tick filename")
            root = Path(report["attempts"][row["attempt_index"]]["attempt"])
            tick_raw = (root / "batches" / row["file"]).read_bytes()
            if hashlib.sha256(tick_raw).hexdigest() != row["sha256"]:
                raise ValueError("Tick file fingerprint changed")
            values = [int(r["time_msc"]) for r in csv.DictReader(io.StringIO(tick_raw.decode()))]
            lo, hi = (stamp - EPOCH for stamp in (start, end))
            if len(values) != row["rows"] or any(not lo // MILLISECOND <= t < hi // MILLISECOND for t in values):
                raise ValueError("Tick rows disagree with reconciliation")
            ticks.extend(values)
        start = end
    width = RADIUS // MILLISECOND
    before = [t for t in ticks if bound_ms - width <= t < bound_ms]
    after = [t for t in ticks if bound_ms <= t < bound_ms + width]
    return {
        "boundary_native": boundary.isoformat(), "probe_radius_minutes": 12,
        "reconciliation_sha256": hashlib.sha256(raw).hexdigest(),
        "request_status_counts": dict(counts), "windows": selected,
        "all_probe_requests_accounted_for": sum(counts.values()) == counts["saved_verified"] + counts["reported_empty"],
        "observed_ticks_before": len(before), "observed_ticks_at_or_after": len(after),
        "closest_before_native": (EPOCH + max(before) * MILLISECOND).isoformat() if before else None,
        "closest_at_or_after_native": (EPOCH + min(after) * MILLISECOND).isoformat() if after else None,
        "quote_session_verified": False, "trade_session_verified": False,
        "utc_mapping_verified": False, "holdout_scored": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reconciliation", type=Path)
    parser.add_argument("boundary", type=native_bound)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = probe(args.reconciliation, args.boundary)
    with args.output.open("x") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(report["request_status_counts"])
    if not report["all_probe_requests_accounted_for"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

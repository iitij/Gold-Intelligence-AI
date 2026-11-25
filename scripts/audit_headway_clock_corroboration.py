"""Measure exact clock observations corroborated in a reconciled native quote range."""

import argparse
import csv
import hashlib
import io
import json
from bisect import bisect_right
from collections import Counter
from datetime import timedelta
from pathlib import Path

from audit_headway_tick_batches import EPOCH, native_bound
from build_headway_clock_receipt import build

MS = timedelta(milliseconds=1)


def read_receipt(receipt):
    raw = receipt.read_bytes()
    anchor = json.loads(raw)
    root = receipt.parent
    start, end = (native_bound(anchor["export_audit"][key]) for key in (
        "requested_native_start", "requested_native_end_exclusive",
    ))
    backed = build(root / "clock.jsonl", root / "ntp-before.txt", root / "ntp-after.txt",
                   root / "batches", root / "export.log", start, end,
                   anchor["native_minus_utc_seconds"], capture_matches=True)
    ticks = backed.pop("matched_native_ms")
    if backed != anchor:
        raise ValueError("Clock receipt does not match its re-audited source files")
    return anchor, ticks, hashlib.sha256(raw).hexdigest()


def report_corroboration(reconciliation, expected, receipts):
    raw = reconciliation.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Reconciliation fingerprint differs")
    report = json.loads(raw)
    if ((report["schema_version"], report["server"], report["symbol"]) != (1, "Headway-Demo", "XAUUSD")
            or report["all_requests_reconciled"] is not True):
        raise ValueError("Expected a fully accounted Headway-Demo XAUUSD report")
    windows, starts = report["windows"], []
    last_end = None
    for window in windows:
        start, end = ((native_bound(window[key]) - EPOCH) // MS
                      for key in ("native_start", "native_end_exclusive"))
        if (last_end is not None and start != last_end) or not 0 < end - start <= 120000:
            raise ValueError("Expected contiguous reconciled native windows")
        starts.append(start)
        last_end = end
    cached, directly_matched = {}, {}
    checked = set()
    outcomes = []
    for path in receipts:
        anchor, ticks, receipt_hash = read_receipt(path)
        if receipt_hash in checked:
            raise ValueError("Repeated clock receipt")
        checked.add(receipt_hash)
        counts = Counter()
        for tick in ticks:
            if not starts or not starts[0] <= tick < last_end:
                counts["out_of_range"] += 1
                continue
            i = bisect_right(starts, tick) - 1
            window = windows[i]
            if window["status"] != "saved_verified":
                counts["missing_saved_window"] += 1
                continue
            if i not in cached:
                row = next(r for r in window["observations"] if r["status"] == "saved_verified")
                name = f"{EPOCH + starts[i] * MS:%Y%m%dT%H%M%S}_{native_bound(window['native_end_exclusive']):%Y%m%dT%H%M%S}.csv"
                if row["file"] != name:
                    raise ValueError("Unexpected reconciled tick file name")
                root = Path(report["attempts"][row["attempt_index"]]["attempt"])
                tick_bytes = (root / "batches" / name).read_bytes()
                if hashlib.sha256(tick_bytes).hexdigest() != row["sha256"]:
                    raise ValueError("Reconciled tick fingerprint changed")
                cached[i] = {int(r["time_msc"]) for r in csv.DictReader(io.StringIO(tick_bytes.decode()))}
            if tick not in cached[i]:
                counts["missing_timestamp"] += 1
                continue
            counts["matched_reconciled_export"] += 1
            offset = anchor["native_minus_utc_seconds"]
            if directly_matched.setdefault(tick, offset) != offset:
                raise ValueError("Direct clock offsets conflict for the same native timestamp")
        outcomes.append({"receipt_sha256": receipt_hash,
                         "first_observation_utc": anchor["first_host_observation_utc"],
                         "last_observation_utc": anchor["last_host_observation_utc"],
                         "observed_offset_seconds": anchor["native_minus_utc_seconds"],
                         "counts": dict(counts)})
    with_matches = Counter(bisect_right(starts, tick) - 1 for tick in directly_matched)
    return {"schema_version": 1, "reconciliation_sha256": expected, "receipts": outcomes,
            "distinct_matched_native_timestamps": len(directly_matched),
            "request_windows": len(windows), "windows_with_direct_match": len(with_matches),
            "windows_without_direct_match": len(windows) - len(with_matches),
            "direct_match_windows": [{"native_start": windows[i]["native_start"], "distinct_matches": count}
                                     for i, count in sorted(with_matches.items())],
            "full_window_offset_verified": False, "holdout_scored": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reconciliation", type=Path)
    parser.add_argument("sha256")
    parser.add_argument("output", type=Path)
    parser.add_argument("--clock-receipt", type=Path, action="append", required=True)
    args = parser.parse_args()
    result = report_corroboration(args.reconciliation, args.sha256, args.clock_receipt)
    with args.output.open("x") as output:
        output.write(json.dumps(result, indent=2) + "\n")
    print(f"{result['distinct_matched_native_timestamps']} distinct directly matched timestamps; "
          f"{result['windows_with_direct_match']}/{result['request_windows']} windows with a direct match")


if __name__ == "__main__":
    main()

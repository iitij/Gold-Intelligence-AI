"""Stage reconciled XAUUSD quotes on their native clock without assigning UTC."""

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from audit_headway_tick_batches import EPOCH, native_bound

RAW_FIELDS = ["time_msc", "bid", "ask", "flags"]
NATIVE_FIELDS = ["native_time_msc", *RAW_FIELDS[1:]]
MS = timedelta(milliseconds=1)
STEP = timedelta(minutes=2)


def fingerprints(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stage(report, output):
    windows = report["windows"]
    if not windows:
        raise ValueError("Expected at least one reconciled window")
    counts = Counter()
    first = last = previous_end = None
    total = 0
    for window in windows:
        lo, hi = (native_bound(window[k]) for k in ("native_start", "native_end_exclusive"))
        if not lo < hi <= lo + STEP or (previous_end is not None and lo != previous_end):
            raise ValueError("Expected contiguous native request windows")
        previous_end = hi
        status = window["status"]
        if status not in ("saved_verified", "reported_empty"):
            raise ValueError("Cannot stage a report with unresolved or conflicting windows")
        counts[status] += 1
        witnesses = [r for r in window["observations"] if r["status"] == status]
        if not witnesses:
            raise ValueError("Reconciliation window has no supporting observation")
        if status == "reported_empty":
            continue
        row = witnesses[0]
        if {(w["sha256"], w["rows"]) for w in witnesses} != {(row["sha256"], row["rows"])}:
            raise ValueError("Saved witnesses disagree")
        lower, upper = ((value - EPOCH) // MS for value in (lo, hi))
        expected_name = f"{lo:%Y%m%dT%H%M%S}_{hi:%Y%m%dT%H%M%S}.csv"
        root = Path(report["attempts"][row["attempt_index"]]["attempt"])
        if row["file"] != expected_name:
            raise ValueError("Unexpected tick filename")
        raw = (root / "batches" / expected_name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError(f"Reconciled tick fingerprint changed: {expected_name}")
        reader = csv.reader(io.StringIO(raw.decode(), newline=""), strict=True)
        if next(reader, None) != RAW_FIELDS:
            raise ValueError("Unexpected MT5 tick header")
        count = 0
        for tick in reader:
            ms_text, bid_text, ask_text, flags_text = tick
            stamp, bid, ask, flags = int(ms_text), Decimal(bid_text), Decimal(ask_text), int(flags_text)
            if (not lower <= stamp < upper or (last is not None and last > stamp)
                    or not bid.is_finite() or not ask.is_finite() or not 0 < bid <= ask
                    or not 0 <= flags < 2**32):
                raise ValueError(f"Invalid native tick in {expected_name}")
            first = stamp if first is None else first
            last = stamp
            count += 1
            output.writerow(tick)
        if not count or count != row["rows"]:
            raise ValueError(f"Reconciled tick count changed: {expected_name}")
        total += count
    if not total or counts != report["window_status_counts"]:
        raise ValueError("Staged counts disagree with expected quote evidence")
    return {"quote_rows": total, "window_status_counts": dict(counts),
            "first_quote_native_ms": first, "last_quote_native_ms": last,
            "requested_native_start": windows[0]["native_start"],
            "requested_native_end_exclusive": windows[-1]["native_end_exclusive"]}


def assemble(report_path, expected, output):
    raw = report_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Reconciliation fingerprint differs")
    report = json.loads(raw)
    if ((report["schema_version"], report["server"], report["symbol"]) != (1, "Headway-Demo", "XAUUSD")
            or report["all_requests_reconciled"] is not True):
        raise ValueError("Expected a fully accounted Headway-Demo XAUUSD reconciliation")
    if output.exists():
        raise FileExistsError(output)
    with TemporaryDirectory(dir=output.parent) as tmp:
        staged = Path(tmp) / "quotes-native.csv"
        with staged.open("x", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(NATIVE_FIELDS)
            stats = stage(report, writer)
        manifest = {"schema_version": 1, "server": "Headway-Demo", "symbol": "XAUUSD",
                    "reconciliation_sha256": expected, "quotes_native_sha256": fingerprints(staged),
                    "time_basis": "native_mt5_milliseconds_not_utc",
                    **stats, "utc_mapping_verified": False, "market_coverage_verified": False,
                    "holdout_scored": False, "evaluation_ready": False}
        record = Path(tmp) / "manifest.json"
        record.write_text(json.dumps(manifest, indent=2) + "\n")
        output.mkdir(mode=0o700)
        staged.rename(output / staged.name)
        record.rename(output / record.name)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reconciliation", type=Path)
    parser.add_argument("sha256")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(assemble(args.reconciliation, args.sha256, args.output), indent=2))


if __name__ == "__main__":
    main()

"""Audit the frozen Headway exporter's two-minute requests on the native clock."""

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

REQUEST_HEADER = re.compile(r"Headway-Demo verified; requesting XAUUSD from (.+) to (.+)")
REQUEST_WINDOW = re.compile(r"Request (\S+) through (\S+) exclusive")
SAVED = re.compile(r"Saved ([1-9][0-9]*) rows")
BATCH_NAME = re.compile(r"[0-9]{8}T[0-9]{6}_[0-9]{8}T[0-9]{6}\.csv")
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
BATCH = timedelta(minutes=2)
MAX_BATCH_BYTES = 8 * 1024 * 1024


def native_bound(value):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() != timedelta(0) or stamp.second or stamp.microsecond:
        raise ValueError("Export bounds must be UTC-encoded native times on whole minutes")
    return stamp


def log_receipts(raw, start, end, expected):
    lines = iter(raw.decode("utf-8").splitlines())
    if next(lines, None) != "Connecting to MT5":
        raise ValueError("Missing MT5 connection start")
    header = REQUEST_HEADER.fullmatch(next(lines, ""))
    if header is None or tuple(map(native_bound, header.groups())) != (start, end):
        raise ValueError("Exporter log identifies a different server, symbol or interval")
    requests = {}
    previous = None
    complete = True
    for line in lines:
        match = REQUEST_WINDOW.fullmatch(line)
        if match is None:
            raise ValueError("Unexpected line in exporter log")
        lower, upper = map(native_bound, match.groups())
        if expected.get(lower) != upper or (previous is not None and lower <= previous):
            raise ValueError("Exporter log describes an unexpected or repeated request")
        previous = lower
        result = next(lines, None)
        if result is None:
            # A process stopped after announcing a request. That does not prove it returned empty.
            complete = False
            break
        saved = SAVED.fullmatch(result)
        if saved is not None:
            requests[lower] = int(saved.group(1))
        elif result == "Empty quote window":
            requests[lower] = 0
        else:
            raise ValueError("Exporter request has no recognized outcome")
    return requests, complete


def audit_file(path, start, end):
    with path.open("rb") as stream:
        raw = stream.read(MAX_BATCH_BYTES + 1)
    if len(raw) > MAX_BATCH_BYTES:
        raise ValueError(f"{path.name}: batch exceeds size limit")
    lower = (start - EPOCH) // timedelta(milliseconds=1)
    upper = (end - EPOCH) // timedelta(milliseconds=1)
    rows = csv.reader(io.StringIO(raw.decode("utf-8"), newline=""), strict=True)
    if next(rows, None) != ["time_msc", "bid", "ask", "flags"]:
        raise ValueError(f"{path.name}: unexpected tick header")
    first = previous = None
    count = same_timestamp = repeated_quote = largest_gap = 0
    quotes_at_stamp = set()
    for fields in rows:
        try:
            stamp_text, bid_text, ask_text, flags_text = fields
            stamp, flags = int(stamp_text), int(flags_text)
            bid, ask = Decimal(bid_text), Decimal(ask_text)
        except (ValueError, InvalidOperation) as exc:
            raise ValueError(f"{path.name}:{rows.line_num}: malformed tick") from exc
        if (not lower <= stamp < upper or (previous is not None and stamp < previous)
                or not 0 <= flags <= 2**32 - 1 or not bid.is_finite()
                or not ask.is_finite() or not 0 < bid <= ask):
            raise ValueError(f"{path.name}:{rows.line_num}: invalid time, flags or Bid/Ask")
        if stamp != previous:
            quotes_at_stamp.clear()
        else:
            same_timestamp += 1
        quote = bid, ask, flags
        repeated_quote += int(quote in quotes_at_stamp)
        quotes_at_stamp.add(quote)
        if previous is not None:
            largest_gap = max(largest_gap, stamp - previous)
        first = stamp if first is None else first
        previous = stamp
        count += 1
    if first is None:
        raise ValueError(f"{path.name}: exporter does not write files for empty requests")
    return {
        "rows": count, "sha256": hashlib.sha256(raw).hexdigest(),
        "first_native_ms": first, "last_native_ms": previous, "max_within_batch_gap_ms": largest_gap,
        "same_timestamp_rows": same_timestamp, "repeated_export_row_count": repeated_quote,
    }


def audit_batches(batches, log, start, end):
    if not start < end or end - start > timedelta(days=60):
        raise ValueError("Use an increasing request interval of at most 60 days")
    if not batches.is_dir():
        raise ValueError("Batch directory does not exist")
    expected = {}
    cursor = start
    while cursor < end:
        expected[cursor] = min(cursor + BATCH, end)
        cursor = expected[cursor]
    expected_names = {f"{a:%Y%m%dT%H%M%S}_{b:%Y%m%dT%H%M%S}.csv" for a, b in expected.items()}
    actual = {p.name: p for p in batches.iterdir() if p.suffix.lower() == ".csv"}
    if any(not BATCH_NAME.fullmatch(name) or name not in expected_names for name in actual):
        raise ValueError("Unexpected batch filename or overlapping request interval")
    log_bytes = log.read_bytes()
    receipts, complete_log = log_receipts(log_bytes, start, end, expected)
    results = []
    largest_gap = 0
    previous = None
    largest_break = None
    for a, b in expected.items():
        name = f"{a:%Y%m%dT%H%M%S}_{b:%Y%m%dT%H%M%S}.csv"
        row = {"requested_native_start": a.isoformat(), "requested_native_end_exclusive": b.isoformat(),
               "file": name if name in actual else None}
        logged = receipts.get(a)
        if name in actual:
            row.update(audit_file(actual[name], a, b))
            if logged is not None and row["rows"] != logged:
                raise ValueError(f"{name}: row count contradicts exporter log")
            row["status"] = "saved_verified" if logged is not None else "file_without_receipt"
            if previous is not None and row["first_native_ms"] - previous > largest_gap:
                largest_gap = row["first_native_ms"] - previous
                largest_break = [previous, row["first_native_ms"]]
            previous = row["last_native_ms"]
        elif logged == 0:
            row["status"] = "reported_empty"
        elif logged is not None:
            row["status"] = "missing_reported_file"
            row["logged_rows"] = logged
        else:
            row["status"] = "unaccounted"
        results.append(row)
    counts = Counter(row["status"] for row in results)
    return {
        "schema_version": 1, "server": "Headway-Demo", "symbol": "XAUUSD",
        "time_basis": "Native MT5 clock encoded as UTC; independent conversion required",
        "export_log_sha256": hashlib.sha256(log_bytes).hexdigest(),
        "log_ends_with_completed_request": complete_log and bool(receipts),
        "requested_native_start": start.isoformat(), "requested_native_end_exclusive": end.isoformat(),
        "expected_windows": len(expected), "window_status_counts": dict(counts),
        "all_request_windows_accounted_for": complete_log
        and counts["saved_verified"] + counts["reported_empty"] == len(expected),
        "total_stored_rows": sum(row.get("rows", 0) for row in results),
        "same_timestamp_rows": sum(row.get("same_timestamp_rows", 0) for row in results),
        "repeated_export_rows": sum(row.get("repeated_export_row_count", 0) for row in results),
        "max_within_batch_gap_ms": max(row.get("max_within_batch_gap_ms", 0) for row in results),
        "max_between_observed_batches_gap_ms": largest_gap,
        "max_between_batch_gap_endpoints_native_ms": largest_break,
        "utc_mapping_verified": False, "holdout_data_complete": False,
        "windows": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batches", type=Path)
    parser.add_argument("log", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--start", required=True, type=native_bound)
    parser.add_argument("--end", required=True, type=native_bound)
    args = parser.parse_args()
    report = audit_batches(args.batches, args.log, args.start, args.end)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(f"Audited {report['expected_windows']} windows and {report['total_stored_rows']} rows")
    if not report["all_request_windows_accounted_for"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

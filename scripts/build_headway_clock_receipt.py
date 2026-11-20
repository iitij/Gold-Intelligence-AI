"""Corroborate one observed Headway clock session against audited native ticks."""

import argparse
import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

from audit_headway_tick_batches import audit_batches, native_bound

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def utc(value):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() != timedelta(0):
        raise ValueError("Expected explicit UTC")
    return stamp


def build(clock, before, after, batches, log, start, end, offset):
    if type(offset) is not int or abs(offset) > 14 * 3600 or offset % 900:
        raise ValueError("Expected a reviewed offset on a 15-minute boundary")
    ntp_bytes = {path: path.read_bytes() for path in (before, after)}
    if any(raw.strip() != b"NTPSynchronized=yes" for raw in ntp_bytes.values()):
        raise ValueError("Both host clock checks must be synchronized")
    audit = audit_batches(batches, log, start, end)
    if not audit["all_request_windows_accounted_for"]:
        raise ValueError("Native quote export has unaccounted windows")
    native = set()
    for window in audit["windows"]:
        if window["file"] is None:
            continue
        path = batches / window["file"]
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != window["sha256"]:
            raise ValueError("Native quote file changed after auditing")
        native.update(int(row["time_msc"]) for row in csv.DictReader(raw.decode().splitlines()))

    raw_clock = clock.read_bytes()
    observations = [json.loads(line) for line in raw_clock.splitlines() if line.strip()]
    if not observations or observations[0]["kind"] != "initial_cached_quote":
        raise ValueError("Missing initial cache observation")
    previous_host = utc(observations[0]["host_utc_after"])
    previous_tick = observations[0]["native_tick_ms"]
    if type(previous_tick) is not int or utc(observations[0]["host_utc_before"]) > previous_host:
        raise ValueError("Invalid initial cache observation")
    matched = []
    unmatched = delayed = 0
    for row in observations[1:]:
        observed_before, observed_after = (utc(row[key]) for key in ("host_utc_before", "host_utc_after"))
        stamp = row["native_tick_ms"]
        if (row["kind"] != "changed_quote" or type(stamp) is not int or stamp <= previous_tick
                or not previous_host <= observed_before <= observed_after):
            raise ValueError("Unexpected clock observation order or kind")
        previous_host, previous_tick = observed_after, stamp
        residual = (EPOCH + timedelta(milliseconds=stamp, seconds=-offset) - observed_after).total_seconds()
        rpc = (observed_after - observed_before).total_seconds()
        if stamp not in native:
            unmatched += 1
        elif not -2 <= residual <= 0.5 or rpc > 1:
            delayed += 1
        else:
            matched.append((observed_after, residual, rpc))

    if len(matched) < 3 or (matched[-1][0] - matched[0][0]).total_seconds() < 2:
        raise ValueError("Insufficient distinct observations corroborate the session offset")
    if matched[0][0].date() != matched[-1][0].date():
        raise ValueError("Use one UTC date per clock receipt")
    residuals = [row[1] for row in matched]
    fingerprints = {str(path): hashlib.sha256(raw).hexdigest() for path, raw in ntp_bytes.items()}
    fingerprints.update({str(clock): hashlib.sha256(raw_clock).hexdigest(), str(log): audit["export_log_sha256"]})
    fingerprints.update({str(batches / row["file"]): row["sha256"] for row in audit["windows"] if row["file"]})
    return {
        "status": "matching_current_headway_demo_quote_clock_and_export",
        "server": "Headway-Demo", "symbol": "XAUUSD", "ntp_before_after": True,
        "native_minus_utc_seconds": offset, "changed_quotes_matched": len(matched),
        "changed_quotes_without_export_match": unmatched, "changed_quotes_outside_latency_limit": delayed,
        "first_host_observation_utc": matched[0][0].isoformat(),
        "last_host_observation_utc": matched[-1][0].isoformat(),
        "residual_seconds": {"min": min(residuals), "median": median(residuals), "max": max(residuals)},
        "rpc_max_seconds": max(row[2] for row in matched), "raw_native_time_only": True,
        "historical_or_holdout_clock_verified": False, "file_sha256": fingerprints,
        "export_audit": audit,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("clock", "ntp_before", "ntp_after", "batches", "log", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--start", type=native_bound, required=True)
    parser.add_argument("--end", type=native_bound, required=True)
    parser.add_argument("--offset-seconds", type=int, required=True)
    args = parser.parse_args()
    result = build(args.clock, args.ntp_before, args.ntp_after, args.batches, args.log,
                   args.start, args.end, args.offset_seconds)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(f"Matched {result['changed_quotes_matched']} synchronized Headway observations")


if __name__ == "__main__":
    main()

"""Capture and audit closed Headway tick requests using a recent session clock receipt."""

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from audit_headway_tick_batches import audit_batches, native_bound
from build_headway_clock_receipt import utc


def validate_bounds(anchor, start, end, now):
    offset = anchor["native_minus_utc_seconds"]
    if (anchor["status"] != "matching_current_headway_demo_quote_clock_and_export"
            or anchor["server"] != "Headway-Demo" or anchor["symbol"] != "XAUUSD"
            or anchor["ntp_before_after"] is not True
            or type(anchor["changed_quotes_matched"]) is not int
            or anchor["changed_quotes_matched"] < 3
            or type(offset) is not int or abs(offset) > 50400 or offset % 900):
        raise ValueError("Expected a corroborated Headway session clock")
    last = utc(anchor["last_host_observation_utc"])
    if not timedelta(0) <= now - last <= timedelta(minutes=30) or last.date() != now.date():
        raise ValueError("Session clock receipt is stale or in the future")
    boundary = end - timedelta(seconds=offset)
    if not start < end or end - start > timedelta(days=1):
        raise ValueError("Expected an increasing native interval of at most one day")
    if now < boundary + timedelta(seconds=2):
        raise ValueError("Requested interval has not closed with the observed session offset")
    return boundary


def synchronized():
    return subprocess.check_output(
        ["timedatectl", "show", "-p", "NTPSynchronized"], timeout=10,
    ).strip() == b"NTPSynchronized=yes"


def win_path(path):
    return "Z:" + str(path.resolve()).replace("/", "\\")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attempt", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--start", type=native_bound, required=True)
    parser.add_argument("--end", type=native_bound, required=True)
    parser.add_argument("--wine", type=Path, required=True)
    parser.add_argument("--win-python", type=Path, required=True)
    parser.add_argument("--terminal", required=True)
    args = parser.parse_args()
    anchor = args.receipt.read_bytes()
    if not synchronized():
        raise SystemExit("Host clock must be synchronized before collection")
    begun = datetime.now(timezone.utc)
    boundary = validate_bounds(json.loads(anchor), args.start, args.end, begun)
    args.attempt.mkdir()
    command = [
        str(args.wine), str(args.win_python), win_path(Path(__file__).with_name("export_headway_ticks.py")),
        win_path(args.attempt / "batches"), "--start", args.start.isoformat(),
        "--end", args.end.isoformat(), "--batch", "--terminal", args.terminal, "--portable",
    ]
    with ((args.attempt / "export.log").open("xb") as out,
          (args.attempt / "export.stderr").open("xb") as err):
        try:
            code = subprocess.run(command, stdout=out, stderr=err, timeout=90).returncode
        except subprocess.TimeoutExpired:
            code = 124
    finished = datetime.now(timezone.utc)
    sync_after = synchronized()
    report = {
        "request_not_before_utc": begun.isoformat(), "request_finished_utc": finished.isoformat(),
        "requested_native_start": args.start.isoformat(),
        "requested_native_end_exclusive": args.end.isoformat(),
        "end_utc_under_session_offset": boundary.isoformat(),
        "session_receipt_sha256": hashlib.sha256(anchor).hexdigest(),
        "host_clock_synchronized_after": sync_after,
        "export_exit_code": code, "historical_offset_verified": False, "holdout_scored": False,
    }
    if (args.attempt / "batches").is_dir():
        report["audit"] = audit_batches(args.attempt / "batches", args.attempt / "export.log",
                                        args.start, args.end)
    report["closed_request_receipt_accepted"] = (code == 0 and sync_after and finished >= begun
        and report.get("audit", {}).get("all_request_windows_accounted_for", False))
    with (args.attempt / "closed-request.json").open("x") as out:
        json.dump(report, out, indent=2)
        out.write("\n")
    print(report.get("audit", {}).get("window_status_counts", {}))
    if not report["closed_request_receipt_accepted"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

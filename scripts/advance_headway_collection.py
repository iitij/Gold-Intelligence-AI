"""Run one closed Headway acquisition checkpoint and extend its audited report."""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from audit_headway_tick_batches import EPOCH, native_bound
from collect_closed_headway_batches import validate_bounds

STEP = timedelta(minutes=2)
MAX_REQUEST = timedelta(days=1)
SCRIPTS = Path(__file__).resolve().parent


def closed_end(last, offset, now):
    """Retain the report's grid and leave the collector's closure margin."""
    if (last - EPOCH) % STEP:
        raise ValueError("Previous report must end on the two-minute native grid")
    eligible = now + timedelta(seconds=offset - 2)
    latest = EPOCH + (eligible - EPOCH) // STEP * STEP
    return min(latest, last + MAX_REQUEST)


def run(script, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], check=False).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("previous", type=Path)
    parser.add_argument("previous_sha256")
    parser.add_argument("attempt", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--previous-clock-receipt", type=Path, action="append", default=[])
    parser.add_argument("--wine", type=Path, required=True)
    parser.add_argument("--win-python", type=Path, required=True)
    parser.add_argument("--terminal", required=True)
    args = parser.parse_args()
    raw = args.previous.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.previous_sha256:
        parser.error("Previous report fingerprint differs")
    old = json.loads(raw)
    if ((old["schema_version"], old["server"], old["symbol"]) != (1, "Headway-Demo", "XAUUSD")
            or old["all_requests_reconciled"] is not True):
        parser.error("Expected a fully accounted Headway-Demo XAUUSD report")
    start = native_bound(old["windows"][0]["native_start"])
    last = native_bound(old["windows"][-1]["native_end_exclusive"])
    anchor = json.loads(args.receipt.read_bytes())
    now = datetime.now(timezone.utc)
    end = closed_end(last, anchor["native_minus_utc_seconds"], now)
    if end <= last:
        print("No additional closed two-minute windows")
        return
    validate_bounds(anchor, last, end, now)
    if (args.output.exists() or not args.output.parent.is_dir() or args.attempt.exists()
            or not args.attempt.parent.is_dir() or args.output.resolve() == args.attempt.resolve()):
        parser.error("Choose distinct new attempt and report paths in existing directories")
    if end - start > timedelta(days=60):
        parser.error("Extended reconciliation would exceed 60 days")

    anchors = dict.fromkeys([*args.previous_clock_receipt, args.receipt])
    known = {hashlib.sha256(p.read_bytes()).hexdigest() for p in anchors}
    for previous in old["attempts"]:
        if "closed_request_sha256" not in previous:
            continue
        receipt = (Path(previous["attempt"]) / "closed-request.json").read_bytes()
        if (hashlib.sha256(receipt).hexdigest() != previous["closed_request_sha256"]
                or json.loads(receipt)["session_receipt_sha256"] not in known):
            parser.error("Previous close receipt differs or its clock receipt is missing")

    code = run("collect_closed_headway_batches.py", args.attempt, "--receipt", args.receipt,
               "--start", last.isoformat(), "--end", end.isoformat(),
               "--wine", args.wine, "--win-python", args.win_python, "--terminal", args.terminal)
    if code:
        raise SystemExit(code)
    prior_options = [item for p in anchors for item in ("--previous-clock-receipt", p)]
    code = run("reconcile_headway_attempts.py", args.output, "--start", start.isoformat(),
               "--end", end.isoformat(), "--previous", args.previous, args.previous_sha256,
               *prior_options, "--guarded-attempt", args.attempt, args.receipt)
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()

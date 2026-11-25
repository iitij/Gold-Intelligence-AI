"""Capture one live Headway clock sample and corroborate it with a separate tick export."""

import argparse
import json
import subprocess
from datetime import timedelta
from pathlib import Path

from audit_headway_tick_batches import EPOCH
from build_headway_clock_receipt import build, utc
from collect_closed_headway_batches import win_path

WINDOW_MS = 120_000
SCRIPTS = Path(__file__).resolve().parent


def sample_bounds(clock, offset):
    samples = []
    for line in clock.read_text().splitlines():
        row = json.loads(line)
        if row["kind"] != "changed_quote":
            continue
        stamp = row["native_tick_ms"]
        before, after = (utc(row[key]) for key in ("host_utc_before", "host_utc_after"))
        corrected = EPOCH + timedelta(milliseconds=stamp, seconds=-offset)
        if -2 <= (corrected - after).total_seconds() <= 0.5 and 0 <= (after - before).total_seconds() <= 1:
            samples.append(stamp)
    if len(samples) < 3:
        raise ValueError("Too few current observations for the proposed session offset")
    first = min(samples) // WINDOW_MS * WINDOW_MS
    end = (max(samples) // WINDOW_MS + 1) * WINDOW_MS
    if end - first > 2 * WINDOW_MS:
        raise ValueError("Clock sample spans more than two native request windows")
    return EPOCH + timedelta(milliseconds=first), EPOCH + timedelta(milliseconds=end)


def ntp(destination):
    value = subprocess.check_output(["timedatectl", "show", "-p", "NTPSynchronized"], timeout=10)
    with destination.open("xb") as stream:
        stream.write(value)
    if value.strip() != b"NTPSynchronized=yes":
        raise ValueError("Host clock is not synchronized")


def call(command, stdout, stderr, timeout):
    with stdout.open("xb") as out, stderr.open("xb") as err:
        subprocess.run(command, stdout=out, stderr=err, check=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--offset-seconds", required=True, type=int)
    parser.add_argument("--seconds", type=int, default=15)
    parser.add_argument("--wine", type=Path, required=True)
    parser.add_argument("--win-python", type=Path, required=True)
    parser.add_argument("--terminal", required=True)
    args = parser.parse_args()
    offset = args.offset_seconds
    if abs(offset) > 50400 or offset % 900 or not 3 <= args.seconds <= 60:
        parser.error("Use a reviewed offset on a quarter-hour boundary and 3–60 observation seconds")
    args.output.mkdir(mode=0o700)
    before, after = (args.output / f"ntp-{label}.txt" for label in ("before", "after"))
    clock, log, batches = (args.output / key for key in ("clock.jsonl", "export.log", "batches"))
    env_command = [str(args.wine), str(args.win_python)]
    terminal_args = ["--terminal", args.terminal, "--portable"]
    ntp(before)
    call([*env_command, win_path(SCRIPTS / "observe_headway_clock.py"),
          "--seconds", str(args.seconds), *terminal_args], clock, args.output / "clock.stderr", args.seconds + 25)
    ntp(after)
    start, end = sample_bounds(clock, offset)
    call([*env_command, win_path(SCRIPTS / "export_headway_ticks.py"), win_path(batches),
          "--start", start.isoformat(), "--end", end.isoformat(), "--batch", *terminal_args],
         log, args.output / "export.stderr", 55)
    receipt = build(clock, before, after, batches, log, start, end, offset)
    with (args.output / "receipt.json").open("x") as stream:
        stream.write(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
    print(f"Matched {receipt['changed_quotes_matched']} live observations. This is not a closed acquisition.")


if __name__ == "__main__":
    main()

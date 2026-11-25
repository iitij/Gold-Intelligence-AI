"""Assemble archived request windows on a provisional zero-offset clock."""
import argparse
import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batches", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    sources = {}
    count = 0
    previous = None
    with args.output.open("x", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["timestamp_utc", "bid", "ask"])
        for day, prefix, hour in ((11, "day-11-", 0), (12, "chunk-", 12), (13, "day-13-", 0)):
            anchor = datetime(2026, 11, day, hour, tzinfo=timezone.utc)
            paths = sorted(args.batches.glob(f"{prefix}*.csv"),
                           key=lambda p: int(p.stem.removeprefix(prefix)))
            if not paths:
                raise ValueError(f"No archived batches for day {day}")
            for path in paths:
                start = anchor + timedelta(minutes=int(path.stem.removeprefix(prefix)))
                lower = int(start.timestamp()) * 1000
                sources[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
                with path.open(newline="") as source:
                    for row in csv.DictReader(source):
                        millis = int(row["time_msc"])
                        if not lower <= millis < lower + 120000:
                            continue
                        bid, ask = Decimal(row["bid"]), Decimal(row["ask"])
                        if previous is not None and millis < previous:
                            raise ValueError("Archived request ordering is inconsistent")
                        if not bid.is_finite() or not ask.is_finite() or not 0 < bid <= ask:
                            raise ValueError("Invalid archived Bid/Ask")
                        previous = millis
                        time = start + timedelta(milliseconds=millis - lower)
                        writer.writerow([time.isoformat(), str(bid), str(ask)])
                        count += 1
    manifest = {
        "clock": "Provisional zero-offset encoding of native times; UTC unverified",
        "rows": count, "sources": sources,
        "output_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }
    args.output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()

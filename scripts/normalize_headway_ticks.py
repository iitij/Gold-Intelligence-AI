"""Convert MT5 tick exports using an explicit offset for its entire interval."""

import argparse
import csv
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def convert(source, output, offset):
    sources = sorted(source.glob("*.csv")) if source.is_dir() else [source]
    previous = None
    count = 0
    first_utc = None
    max_gap_ms = 0
    writer = csv.writer(output)
    writer.writerow(["timestamp_utc", "bid", "ask"])
    for source in sources:
        with source.open(newline="") as stream:
            rows = csv.DictReader(stream)
            if rows.fieldnames != ["time_msc", "bid", "ask", "flags"]:
                raise ValueError("Unexpected MT5 tick header")
            first = True
            for row in rows:
                timestamp = int(row["time_msc"])
                bid, ask = Decimal(row["bid"]), Decimal(row["ask"])
                if (
                    (
                        previous is not None
                        and (timestamp < previous or (first and timestamp == previous))
                    )
                    or not bid.is_finite()
                    or not ask.is_finite()
                    or not 0 < bid <= ask
                ):
                    raise ValueError(f"Invalid tick at line {rows.line_num}")
                first = False
                if previous is not None:
                    max_gap_ms = max(max_gap_ms, timestamp - previous)
                previous = timestamp
                utc = EPOCH + timedelta(milliseconds=timestamp, seconds=-offset)
                formatted = utc.isoformat(timespec="milliseconds")
                if first_utc is None:
                    first_utc = formatted
                writer.writerow([formatted, bid, ask])
                count += 1
    if not count:
        raise ValueError("No tick rows")
    return {"rows": count, "first_utc": first_utc, "last_utc": formatted, "max_gap_ms": max_gap_ms}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--offset-seconds", type=int, required=True)
    parser.add_argument("--offset-evidence", required=True)
    args = parser.parse_args()
    sources = sorted(args.source.glob("*.csv")) if args.source.is_dir() else [args.source]
    hashes = {}
    for path in sources:
        with path.open("rb") as source:
            hashes[path.name] = hashlib.file_digest(source, "sha256").hexdigest()
    with NamedTemporaryFile(mode="w", newline="", dir=args.output.parent) as temp:
        coverage = convert(args.source, temp, args.offset_seconds)
        temp.flush()
        with open(temp.name, "rb") as normalized:
            output_hash = hashlib.file_digest(normalized, "sha256").hexdigest()
        os.link(temp.name, args.output)
    print(
        json.dumps(
            {
                **(
                    {"raw_sha256_by_file": hashes}
                    if args.source.is_dir()
                    else {"raw_sha256": hashes[args.source.name]}
                ),
                **coverage,
                "normalized_sha256": output_hash,
                "offset_seconds": args.offset_seconds,
                "offset_evidence": args.offset_evidence,
            }
        )
    )


if __name__ == "__main__":
    main()

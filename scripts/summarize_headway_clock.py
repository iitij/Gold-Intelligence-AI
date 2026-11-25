"""Summarize observed offsets from changed Headway quotes."""

import argparse
import json
from pathlib import Path
from statistics import median


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    args = parser.parse_args()
    with args.capture.open() as stream:
        observations = [json.loads(line) for line in stream if line.strip()]
    changes = [row for row in observations if row["kind"] == "changed_quote"]
    offsets = [row["native_minus_host_seconds"] for row in changes]
    print(json.dumps({
        "changed_quotes": len(changes),
        "median_native_minus_host_seconds": median(offsets) if offsets else None,
        "min_native_minus_host_seconds": min(offsets) if offsets else None,
        "max_native_minus_host_seconds": max(offsets) if offsets else None,
        "first_observed_utc": changes[0]["host_utc_after"] if changes else None,
        "last_observed_utc": changes[-1]["host_utc_after"] if changes else None,
    }, indent=2))


if __name__ == "__main__":
    main()

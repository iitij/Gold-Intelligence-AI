"""Apply explicitly evidenced research time intervals without discarding unmapped bars."""
import argparse
import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from goldintel.data.mt5_csv import COLUMNS, TIME_FORMAT, validate_mt5_csv

METADATA = ["source_row", "mapping_id", "native_minus_utc_seconds", "timestamp_utc_inferred"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def intervals_from_config(config):
    if (config["schema_version"] != 1 or config["symbol"] != "XAUUSD"
            or config["status"] != "research_inference_from_official_notices_and_archived_session_bounds"):
        raise ValueError("Unsupported research time-mapping policy")
    intervals = []
    seen = set()
    for record in config["intervals"]:
        start = datetime.fromisoformat(record["native_start"])
        end = datetime.fromisoformat(record["native_end_exclusive"])
        offset = record["offset_seconds"]
        if (start.tzinfo is not None or end.tzinfo is not None or start >= end
                or isinstance(offset, bool) or not isinstance(offset, int) or abs(offset) > 14 * 3600
                or not record["id"] or record["id"] in seen
                or not record["sources"] or any(s not in config["sources"] for s in record["sources"])):
            raise ValueError("Invalid interval, evidence references or native chronology")
        seen.add(record["id"])
        intervals.append((start, end, offset, record["id"]))
    intervals.sort()
    if not intervals or any(left[1] > right[0] for left, right in zip(intervals, intervals[1:])):
        raise ValueError("Empty or overlapping time-mapping intervals")
    return intervals


def map_source(source, policy, output):
    config = json.loads(policy.read_text())
    intervals = intervals_from_config(config)
    audit = validate_mt5_csv(source, expected_symbol="XAUUSD")
    if audit.source_sha256 != config["source_sha256"]:
        raise ValueError("Broker source fingerprint differs from the mapping policy")
    output.mkdir(parents=True)
    counts = {item[3]: 0 for item in intervals}
    unmapped = 0
    previous_utc = None
    previous_native = None
    with source.open(encoding="utf-8-sig", newline="") as stream, (output / "mapped.csv").open("x", newline="") as mapped, (
        output / "unmapped.csv"
    ).open("x", newline="") as unknown:
        mapped_writer = csv.DictWriter(mapped, fieldnames=[*COLUMNS, *METADATA])
        unknown_writer = csv.DictWriter(unknown, fieldnames=[*COLUMNS, "source_row"])
        mapped_writer.writeheader()
        unknown_writer.writeheader()
        for index, row in enumerate(csv.DictReader(stream)):
            native = datetime.strptime(row["server_time"], TIME_FORMAT)
            selected = next((item for item in intervals if item[0] <= native < item[1]), None)
            if selected is None:
                unknown_writer.writerow({**row, "source_row": index})
                unmapped += 1
                continue
            _, _, offset, identifier = selected
            utc = (native - timedelta(seconds=offset)).replace(tzinfo=timezone.utc)
            if previous_utc is not None and utc <= previous_utc:
                raise ValueError("Mapped bars are not strictly chronological in UTC")
            previous_utc, previous_native = utc, native
            mapped_writer.writerow({**row, "source_row": index, "mapping_id": identifier,
                                    "native_minus_utc_seconds": offset,
                                    "timestamp_utc_inferred": utc.isoformat()})
            counts[identifier] += 1
    if sum(counts.values()) + unmapped != audit.rows:
        raise ValueError("Source-row coverage mismatch")
    if digest(source) != audit.source_sha256:
        raise ValueError("Source changed during time mapping")
    manifest = {
        "source": str(source), "source_sha256": audit.source_sha256,
        "policy": str(policy), "policy_sha256": digest(policy),
        "script_sha256": digest(Path(__file__)), "source_rows": audit.rows,
        "mapped_rows": sum(counts.values()), "unmapped_rows": unmapped,
        "mapping_counts": counts, "last_mapped_native": str(previous_native),
        "files": {name: digest(output / name) for name in ("mapped.csv", "unmapped.csv")},
        "mapping_status": config["status"], "historical_utc_verified": False,
        "approved_for_training_or_trading": False,
        "limitations": [
            "Continuity and archived-demo applicability remain research assumptions",
            "Unmapped bars retain original native timestamps; no automatic seasonal fallback",
            "Inferred timestamps must not be silently treated as independently verified UTC",
        ],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = map_source(args.source, args.policy, args.output)
    print(f"MAPPED {report['mapped_rows']}; PRESERVED UNMAPPED {report['unmapped_rows']}")


if __name__ == "__main__":
    main()

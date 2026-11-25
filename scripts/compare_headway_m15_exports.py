"""Check that a new Headway-Demo M15 export extends the old native-time history."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from goldintel.data.mt5_csv import COLUMNS, validate_mt5_csv


def read(path):
    inspection = validate_mt5_csv(path, expected_symbol="XAUUSD")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != inspection.source_sha256:
        raise ValueError("M15 source changed after validating")
    rows = {row["server_time"]: row for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))}
    return inspection, rows


def compare(previous, current):
    old_audit, old = read(previous)
    new_audit, new = read(current)
    common = sorted(old.keys() & new.keys())
    removed = sorted(old.keys() - new.keys())
    added = sorted(new.keys() - old.keys())
    old_end = max(old)
    revisions = []
    for key in common:
        fields = [field for field in COLUMNS if old[key][field] != new[key][field]]
        if fields:
            revisions.append({"native_open": key, "changed_fields": fields,
                              "previous": {f: old[key][f] for f in fields}, "current": {f: new[key][f] for f in fields}})
    added_before_tail = [stamp for stamp in added if stamp <= old_end]
    return {
        "schema_version": 1, "server": "Headway-Demo", "symbol": "XAUUSD", "timeframe": "M15",
        "previous_sha256": old_audit.source_sha256, "current_sha256": new_audit.source_sha256,
        "previous_rows": old_audit.rows, "current_rows": new_audit.rows,
        "common_rows": len(common), "unchanged_common_rows": len(common) - len(revisions),
        "new_tail_native_opens": [stamp for stamp in added if stamp > old_end],
        "inserted_native_opens_before_tail": added_before_tail,
        "removed_native_opens": removed, "revised_rows": revisions,
        "history_preserved": not (removed or added_before_tail or revisions),
        "utc_mapping_verified": False, "market_coverage_verified": False, "holdout_scored": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("previous", "current", "output"):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    report = compare(args.previous, args.current)
    with args.output.open("x") as output:
        output.write(json.dumps(report, indent=2) + "\n")
    print(f"{report['unchanged_common_rows']} unchanged bars; {len(report['new_tail_native_opens'])} new tail bars")
    return 0 if report["history_preserved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

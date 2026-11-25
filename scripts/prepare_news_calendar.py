"""Audit point-in-time availability of sourced schedule records."""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from goldintel.research.news_blackout import CalendarVersion


def prepare(path):
    document = json.loads(path.read_text())
    usable = []
    incomplete = []
    for row in document["events"]:
        event_id = f'{row["event"]}-{row["reference_period"]}'
        required = ("schedule_known_by_utc", "schedule_known_by_source", "revised_schedule_utc")
        missing = [field for field in required if not row.get(field)]
        if missing:
            incomplete.append({"event_id": event_id, "missing": missing})
            continue
        version = CalendarVersion(
            event_id=event_id,
            known_at_utc=datetime.fromisoformat(row["schedule_known_by_utc"]),
            scheduled_at_utc=datetime.fromisoformat(row["revised_schedule_utc"]),
            canceled=row["canceled"],
            source_id=row["schedule_known_by_source"],
        )
        usable.append({
            "event_id": version.event_id,
            "known_at_utc": version.known_at_utc.isoformat(),
            "scheduled_at_utc": version.scheduled_at_utc.isoformat(),
            "canceled": version.canceled, "source_id": version.source_id,
        })
    return {
        "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "calendar_complete": False, "usable_versions": usable, "incomplete_records": incomplete,
        "training_status": "Incomplete calendar and unresolved broker UTC mapping",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with args.output.open("x") as stream:
        json.dump(prepare(args.input), stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()

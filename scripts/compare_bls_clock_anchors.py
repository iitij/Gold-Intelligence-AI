"""Compare timing hypotheses using historical volatility around BLS embargo times."""

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from goldintel.data.mt5_csv import TIME_FORMAT, validate_mt5_csv

ZERO = Decimal(0)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_ranges(path, expected):
    audit = validate_mt5_csv(path, expected_symbol="XAUUSD")
    if audit.source_sha256 != expected:
        raise ValueError("Clock diagnostic requires exact registered source bytes")
    ranges = {}
    with path.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            stamp = datetime.strptime(row["server_time"], TIME_FORMAT)
            price = Decimal(row["open"])
            ranges[stamp] = (Decimal(row["high"]) - Decimal(row["low"])) / price * 10_000
    if digest(path) != expected:
        raise ValueError("Source changed during clock diagnostic")
    return ranges


def parse_release(row, release_zone):
    native = datetime.fromisoformat(row["release_local"])
    if native.tzinfo is not None or native.hour != 8 or native.minute != 30 or native.second or native.microsecond:
        raise ValueError("Expected the sourced 08:30 Eastern embargo without an embedded offset")
    return native.replace(tzinfo=release_zone).astimezone(timezone.utc)


def event_result(release, feeds, offsets, control_offsets, other_event_dates, minimum):
    utc_naive = release.replace(tzinfo=None)
    expected = {offset: utc_naive + timedelta(minutes=offset) for offset in offsets}
    common = []
    excluded = {}
    for shift in control_offsets:
        day = (release + timedelta(days=shift)).date()
        if day in other_event_dates:
            excluded[str(day)] = "another_registered_release"
        elif not all(t + timedelta(days=shift) in bars for t in expected.values() for bars in feeds.values()):
            excluded[str(day)] = "missing_common_control_bars"
        else:
            common.append(shift)
    result = {"release_utc": release.isoformat(), "common_controls": [
        (release + timedelta(days=shift)).date().isoformat() for shift in common],
        "excluded_controls": excluded, "feeds": {}}
    if not all(t in bars for t in expected.values() for bars in feeds.values()):
        return {**result, "status": "missing_common_event_bars"}
    if len(common) < minimum:
        return {**result, "status": "insufficient_common_controls"}
    for name, bars in feeds.items():
        cases = []
        for offset, stamp in expected.items():
            controls = [bars[stamp + timedelta(days=shift)] for shift in common]
            baseline = median(controls)
            if baseline <= ZERO:
                return {**result, "status": "nonpositive_control_range", "feeds": {}}
            observed = bars[stamp]
            cases.append({
                "offset_minutes": offset, "bar_native": stamp.isoformat(),
                "range_bps": float(observed), "matched_weekday_control_ranges_bps": list(map(float, controls)),
                "median_control_range_bps": float(baseline), "range_multiple": float(observed / baseline),
                "controls_below_event": sum(value < observed for value in controls),
            })
        extreme = max(case["range_multiple"] for case in cases)
        winners = [case["offset_minutes"] for case in cases if case["range_multiple"] == extreme]
        result["feeds"][name] = {"cases": cases, "largest_range_multiple_offsets": winners}
    return {**result, "status": "compared"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--feeds", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.plan.read_bytes()
    plan = json.loads(raw)
    offsets = plan["candidate_native_offsets_minutes"]
    control_offsets = plan["control_day_offsets"]
    minimum = plan["minimum_common_control_days"]
    if (plan["schema_version"] != 1 or plan["release_time_zone"] != "America/New_York"
            or offsets != [60, 120, 180, 240] or control_offsets != [-21, -14, -7, 7, 14, 21]
            or minimum != 3):
        raise ValueError("Unsupported clock diagnostic plan")
    if len(args.feeds) != len(plan["source_sha256"]) or {p.name for p in args.feeds} != set(plan["source_sha256"]):
        raise ValueError("Supply exactly the broker sources declared in the plan")
    zone = ZoneInfo(plan["release_time_zone"])
    releases = [parse_release(row, zone) for row in plan["events"]]
    dates = {t.date() for t in releases}
    if not releases or len(dates) != len(releases):
        raise ValueError("Expected nonempty unique release dates")
    feeds = {p.name: read_ranges(p, plan["source_sha256"][p.name]) for p in args.feeds}
    rows = [{**row, **event_result(t, feeds, offsets, control_offsets, dates, minimum)}
            for row, t in zip(plan["events"], releases, strict=True)]
    output = {
        "schema_version": 1, "plan_sha256": hashlib.sha256(raw).hexdigest(),
        "script_sha256": digest(Path(__file__)), "source_sha256": plan["source_sha256"],
        "event_status_counts": dict(Counter(row["status"] for row in rows)),
        "events": rows, "historical_utc_verified": False, "approved_for_training_or_trading": False,
        "limitations": [
            "Embargo timestamps are official UTC anchors for announcements, not observed quote arrival times",
            "Range maxima can result from intraday seasonality, other news, holidays or feed transients",
            "Weekday controls can contain other announcements and span clock transitions",
            "The broker price series can share upstream data; their votes are not independent",
            "This exploratory comparison does not authorize applying any offset to historical prices",
        ],
    }
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print("Clock diagnostic completed", output["event_status_counts"])


if __name__ == "__main__":
    main()

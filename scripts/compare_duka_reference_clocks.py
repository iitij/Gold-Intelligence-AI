"""Cross-check archived broker clocks and nominal HistData UTC against daily Dukascopy BID bars."""
import argparse
import csv
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from statistics import median

from goldintel.data.dukascopy import read_bid_m15
from goldintel.data.histdata import read_m15
from goldintel.data.mt5_csv import TIME_FORMAT, validate_mt5_csv


def compare(dukascopy, histdata, feeds, expected_days=None):
    reference, _ = read_m15(histdata)
    hashes = {str(histdata): hashlib.sha256(histdata.read_bytes()).hexdigest()}
    broker_data = {}
    for path in feeds:
        audit = validate_mt5_csv(path, expected_symbol="XAUUSD")
        hashes[str(path)] = audit.source_sha256
        with path.open(encoding="utf-8-sig", newline="") as stream:
            broker_data[path.name] = {
                datetime.strptime(row["server_time"], TIME_FORMAT).replace(tzinfo=timezone.utc): Decimal(row["close"])
                for row in csv.DictReader(stream)
            }
    days = []
    for folder in sorted(dukascopy.iterdir()):
        path = folder / "BID_candles_min_1.bi5"
        if not folder.is_dir() or not path.exists():
            continue
        day = datetime.strptime(folder.name, "%Y%m%d").date()
        if expected_days is not None and day not in expected_days:
            continue
        provenance_path = folder / "provenance.json"
        provenance = json.loads(provenance_path.read_text())
        expected_url = (f"https://datafeed.dukascopy.com/datafeed/XAUUSD/{day.year}/"
                        f"{day.month - 1:02d}/{day.day:02d}/BID_candles_min_1.bi5")
        if (provenance["sha256"] != hashlib.sha256(path.read_bytes()).hexdigest()
                or provenance["url"] != expected_url):
            raise ValueError("Daily reference provenance or date mismatch")
        bars, quality = read_bid_m15(path, day)
        hashes[str(provenance_path)] = hashlib.sha256(provenance_path.read_bytes()).hexdigest()
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        results = []
        for feed, prices in broker_data.items():
            cohort = [t for t in sorted(prices) if t.date() == day and all(
                t - timedelta(hours=h) in bars for h in (1, 2, 3)
            )]
            for hours in (1, 2, 3):
                errors = [abs(prices[t] - bars[t - timedelta(hours=hours)]["close"]) for t in cohort]
                results.append({"feed": feed, "native_minus_duka_UTC_hypothesis_hours": hours,
                                "common_bars": len(errors),
                                "median_abs_close_difference": str(median(errors)) if errors else None})
        cohort = [t for t in bars if all(t + timedelta(hours=h) in reference for h in (-1, 0, 1))]
        for hours in (-1, 0, 1):
            errors = [abs(bars[t]["close"] - reference[t + timedelta(hours=hours)]["close"]) for t in cohort]
            results.append({"feed": "HistData_vs_Dukascopy",
                            "histdata_nominal_UTC_time_minus_duka_UTC_hours": hours,
                            "common_bars": len(errors),
                            "median_abs_close_difference": str(median(errors)) if errors else None,
                            "exact_close_matches": sum(error == 0 for error in errors)})
        days.append({"date": str(day), "dukascopy_quality": quality, "comparisons": results})
    if not days:
        raise ValueError("No daily Dukascopy files")
    if expected_days is not None and {date.fromisoformat(day["date"]) for day in days} != set(expected_days):
        raise ValueError("Some requested daily reference files are missing")
    return {"source_sha256": hashes, "days": days,
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "limitations": ["Candidate price-alignment diagnostics; not a complete historical UTC policy",
                            "Shared upstream data can make the two reference providers dependent",
                            "No timestamps corrected automatically; source files remain unchanged"],
            "training_ready": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dukascopy", required=True, type=Path)
    parser.add_argument("--histdata", required=True, type=Path)
    parser.add_argument("--feeds", required=True, nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dates", nargs="+", type=date.fromisoformat)
    args = parser.parse_args()
    report = compare(args.dukascopy, args.histdata, args.feeds, args.dates)
    with args.output.open("x") as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"Compared {len(report['days'])} daily files")


if __name__ == "__main__":
    main()

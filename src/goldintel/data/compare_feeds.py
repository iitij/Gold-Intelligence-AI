"""Deterministic comparison of validated M15 exports in server time only."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from goldintel.data.mt5_csv import TIME_FORMAT, MarketDataError, load_validated_mt5_csv


def compare_feeds(left: Path, right: Path, *, left_symbol: str, right_symbol: str,
                  threshold: Decimal = Decimal("5")) -> dict:
    """Report discrepancies without identifying either feed as ground truth.

    Matching server labels is exploratory; it does not establish equal UTC instants.
    Decimal strings retain exact exported price precision in the JSON report.
    """
    if not threshold.is_finite() or threshold <= 0:
        raise MarketDataError("threshold must be finite and positive")
    reports = []
    feeds = []
    for path, symbol in ((left, left_symbol), (right, right_symbol)):
        report, records = load_validated_mt5_csv(path, expected_symbol=symbol)
        reports.append(asdict(report))
        feeds.append({datetime.strptime(r["server_time"], TIME_FORMAT):
                      {k: Decimal(r[k]) for k in ("open", "high", "low", "close")}
                      for r in records})
    a, b = feeds
    common = sorted(a.keys() & b.keys())
    if not common:
        raise MarketDataError("no shared server timestamps")
    start, end = max(min(a), min(b)), min(max(a), max(b))
    unmatched = []
    for own, other in ((a, b), (b, a)):
        times = sorted(own.keys() - other.keys())
        inside = [t.isoformat() for t in times if start <= t <= end]
        unmatched.append({"total": len(times), "inside_shared_range": inside,
                          "outside_shared_range_count": len(times) - len(inside)})
    outliers, nonoverlap, groups = [], [], []
    month_counts, day_counts = {}, {}
    current = []
    for t in common:
        diff = a[t]["close"] - b[t]["close"]
        if a[t]["high"] < b[t]["low"] or b[t]["high"] < a[t]["low"]:
            nonoverlap.append({"server_time": t.isoformat(), "signed_close_difference": str(diff),
                               "left_low": str(a[t]["low"]), "left_high": str(a[t]["high"]),
                               "right_low": str(b[t]["low"]), "right_high": str(b[t]["high"])})
        if abs(diff) > threshold:
            outliers.append({"server_time": t.isoformat(), "signed_close_difference": str(diff)})
            month = t.strftime("%Y-%m")
            day = t.date().isoformat()
            month_counts[month] = month_counts.get(month, 0) + 1
            day_counts[day] = day_counts.get(day, 0) + 1
            if current and t - current[-1][0] != timedelta(minutes=15):
                groups.append(current)
                current = []
            current.append((t, diff))
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return {
        "format_version": 1, "comparison_basis": "UNVERIFIED_EQUAL_SERVER_LABELS",
        "utc_verified": False, "training_ready": False, "execution_ready": False,
        "threshold_usd_strictly_greater_than": str(threshold),
        "sources": reports, "shared_range_start": start.isoformat(),
        "shared_range_end": end.isoformat(), "matched_candles": len(common),
        "unmatched_left_right": unmatched, "outliers": outliers,
        "outliers_by_month": month_counts, "outliers_by_day": day_counts,
        "nonoverlapping_ranges": nonoverlap,
        "consecutive_outlier_groups": [
            {"start": g[0][0].isoformat(), "end": g[-1][0].isoformat(),
             "candles": len(g),
             "average_signed_difference": str(sum(d for _, d in g) / len(g))}
            for g in sorted(groups, key=lambda g: (-len(g), g[0][0]))],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--left-symbol", required=True)
    parser.add_argument("--right-symbol", required=True)
    args = parser.parse_args()
    try:
        report = compare_feeds(args.left, args.right, left_symbol=args.left_symbol,
                               right_symbol=args.right_symbol)
    except (MarketDataError, OSError) as exc:
        parser.exit(2, f"INVALID COMPARISON: {exc}\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

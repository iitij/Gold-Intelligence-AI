"""Compare raw Headway M15 Bid OHLC with fully covered native tick windows."""

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from audit_headway_tick_batches import BATCH_NAME, EPOCH, native_bound

M15_MS = 900_000
OHLC = ("open", "high", "low", "close")


def read_bars(raw):
    bars = {}
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")):
        stamp = datetime.strptime(row["server_time"], "%Y.%m.%d %H:%M:%S").replace(tzinfo=timezone.utc)
        key = (stamp - EPOCH) // timedelta(milliseconds=1)
        prices = tuple(Decimal(row[field]) for field in OHLC)
        if (key % M15_MS or row["broker_symbol"] != "XAUUSD" or row["timeframe"] != "M15"
                or key in bars or any(not p.is_finite() or p <= 0 for p in prices)
                or not prices[2] <= min(prices[0], prices[3]) <= max(prices[0], prices[3]) <= prices[1]):
            raise ValueError("Invalid native XAUUSD M15 bar")
        bars[key] = prices
    if not bars:
        raise ValueError("M15 export has no bars")
    return bars


def corroborate(reconciled, bar_csv):
    recon_bytes, bar_bytes = reconciled.read_bytes(), bar_csv.read_bytes()
    report = json.loads(recon_bytes)
    if (report["schema_version"], report["server"], report["symbol"]) != (1, "Headway-Demo", "XAUUSD"):
        raise ValueError("Expected a native Headway-Demo XAUUSD reconciliation")
    bars = read_bars(bar_bytes)
    coverage = Counter()
    aggregates = {}
    last = None
    for window in report["windows"]:
        lo, hi = [(native_bound(window[key]) - EPOCH) // timedelta(milliseconds=1)
                  for key in ("native_start", "native_end_exclusive")]
        if not 0 < hi - lo <= 120_000 or (last is not None and lo != last):
            raise ValueError("Reconciliation windows must be contiguous and at most two minutes")
        last = hi
        if window["status"] != "saved_verified":
            continue
        row = next(o for o in window["observations"] if o["status"] == "saved_verified")
        name = row["file"]
        if not BATCH_NAME.fullmatch(name):
            raise ValueError("Unexpected tick filename")
        raw = (Path(report["attempts"][row["attempt_index"]]["attempt"]) / "batches" / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError(f"Reconciled tick fingerprint changed: {name}")
        for key in range(lo // M15_MS * M15_MS, hi, M15_MS):
            coverage[key] += min(hi, key + M15_MS) - max(lo, key)
        previous = lo
        count = 0
        for tick in csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")):
            stamp = int(tick["time_msc"])
            price = Decimal(tick["bid"])
            if not previous <= stamp < hi or not price.is_finite() or price <= 0:
                raise ValueError(f"Invalid or out-of-order tick: {name}")
            previous = stamp
            count += 1
            key = stamp // M15_MS * M15_MS
            if key in aggregates:
                opened, high, low, _ = aggregates[key]
                aggregates[key] = opened, max(high, price), min(low, price), price
            else:
                aggregates[key] = (price,) * 4
        if not count or count != row["rows"]:
            raise ValueError(f"Reconciled tick count changed: {name}")
    checks = []
    for key, duration in sorted(coverage.items()):
        if duration != M15_MS:
            continue
        stamp = (EPOCH + timedelta(milliseconds=key)).isoformat()
        if key not in bars:
            checks.append({"native_open": stamp, "status": "missing_m15"})
            continue
        differences = [field for field, bar, tick in zip(OHLC, bars[key], aggregates[key], strict=True)
                       if bar != tick]
        checks.append({"native_open": stamp, "status": "mismatch" if differences else "matched",
                       "differing_fields": differences})
    counts = Counter(check["status"] for check in checks)
    return {"schema_version": 1, "reconciliation_sha256": hashlib.sha256(recon_bytes).hexdigest(),
            "m15_sha256": hashlib.sha256(bar_bytes).hexdigest(), "m15_export_count": len(bars),
            "native_checks": checks, "status_counts": dict(counts),
            "utc_mapping_verified": False, "market_coverage_verified": False, "holdout_scored": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("reconciliation", "m15", "output"):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    report = corroborate(args.reconciliation, args.m15)
    with args.output.open("x") as output:
        output.write(json.dumps(report, indent=2) + "\n")
    print(report["status_counts"])
    counts = report["status_counts"]
    if not counts.get("matched") or counts.get("mismatch") or counts.get("missing_m15"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()

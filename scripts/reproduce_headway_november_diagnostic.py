"""Reproduce the exploratory replay from native MT5 request batches."""

import argparse
import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from statistics import mean

import pandas as pd
import replay_m15_reversal as replay
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
from research_m15_direction import CUTOFF, prepare


def main():
    parser = argparse.ArgumentParser(description="Reproduce the November Headway diagnostic")
    parser.add_argument("batch_directory", type=Path)
    parser.add_argument("training_csv", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = args.batch_directory
    previous = json.loads((root / "three-day-replay-expanded.json").read_text())
    buckets = {}
    hashes = {}
    counts = {}
    for day, prefix, hour in [(11, "day-11-", 0), (12, "chunk-", 12), (13, "day-13-", 0)]:
        anchor = datetime(2026, 11, day, hour, tzinfo=timezone.utc)
        count = 0
        last = None
        for path in sorted(
            root.glob(f"{prefix}*.csv"), key=lambda p: int(p.stem.removeprefix(prefix))
        ):
            start = anchor + timedelta(minutes=int(path.stem.removeprefix(prefix)))
            start_ms = int(start.timestamp()) * 1000
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
            with path.open(newline="") as stream:
                for row in csv.DictReader(stream):
                    ms = int(row["time_msc"])
                    if not start_ms <= ms < start_ms + 120000:
                        continue
                    bid, ask = Decimal(row["bid"]), Decimal(row["ask"])
                    if (last is not None and ms < last) or not (
                        bid.is_finite() and ask.is_finite() and 0 < bid <= ask
                    ):
                        raise ValueError(f"Invalid quote in {path.name}")
                    last = ms
                    timestamp = start + timedelta(milliseconds=ms - start_ms)
                    boundary = timestamp.replace(
                        minute=timestamp.minute // 15 * 15, second=0, microsecond=0
                    )
                    buckets.setdefault(boundary, []).append((timestamp, bid, ask))
                    count += 1
        counts[day] = count

    features = ["return_1", "return_4", "range", "body"]
    training, audit = prepare(args.training_csv)
    training = training[training.outcome_server_time < CUTOFF]
    replay.START = datetime.fromisoformat(previous["start"])
    ledger = []
    replay.replay(
        buckets, datetime.fromisoformat(previous["end"]), Decimal(0), Decimal(0), ledger=ledger
    )
    fills = {(t["decision"], t["delay_seconds"]): t for t in ledger}
    samples = []
    trades = []
    interior_gaps = []
    for trade in ledger:
        if trade["delay_seconds"] != 0 or any(
            (trade["decision"], delay) not in fills for delay in replay.DELAYS
        ):
            continue
        decision = datetime.fromisoformat(trade["decision"])
        bars = [buckets.get(decision - i * replay.BAR) for i in range(5, 0, -1)]
        closes_at = [decision - i * replay.BAR for i in range(4, -1, -1)]
        if any(
            not bar
            or close_at - bar[-1][0] > replay.WAIT
            or bar[0][0] - (close_at - replay.BAR) > replay.WAIT
            for bar, close_at in zip(bars, closes_at, strict=True)
        ):
            continue
        gap = max(
            (
                (right[0] - left[0]).total_seconds()
                for bar in bars
                for left, right in zip(bar, bar[1:])
            ),
            default=0,
        )
        if gap > 30:
            continue
        interior_gaps.append(gap)
        prices = [quote[1] for quote in bars[-1]]
        close = prices[-1]
        samples.append(
            [
                float(close / bars[-2][-1][1] - 1),
                float(close / bars[0][-1][1] - 1),
                float((max(prices) - min(prices)) / prices[0]),
                float(close / prices[0] - 1),
            ]
        )
        trades.append(trade)

    models = {
        "LightGBM": LGBMClassifier(n_estimators=100, random_state=42, n_jobs=2, verbosity=-1),
        "CatBoost": CatBoostClassifier(
            iterations=100,
            depth=5,
            random_seed=42,
            thread_count=2,
            verbose=False,
            allow_writing_files=False,
        ),
    }
    predictions = {}
    for name, model in models.items():
        model.fit(training[features], training.up)
        predictions[name] = model.predict(pd.DataFrame(samples, columns=features)).reshape(-1)

    results = {}
    for delay in replay.DELAYS:
        paired = [fills[t["decision"], delay] for t in trades]
        results[delay] = {
            "reversal": str(mean(Decimal(t["net_usd_per_ounce"]) for t in paired)),
            "no_trade": "0",
        }
        for name, directions in predictions.items():
            net = []
            for up, trade in zip(directions, paired, strict=True):
                reversal = Decimal(trade["net_usd_per_ounce"])
                net.append(
                    reversal
                    if bool(up) == (trade["side"] == "long")
                    else -reversal - 2 * Decimal(trade["spread_cost"])
                )
            results[delay][name] = str(mean(net))
    report = {
        "status": "exploratory_native_clock_zero_commission_and_slippage",
        "matched_trades": len(trades),
        "training_rows": len(training),
        "training_sha256": audit.source_sha256,
        "training_cutoff": str(CUTOFF),
        "features": features,
        "interior_quote_gap_seconds": {
            "maximum": max(interior_gaps),
            "opportunities_over_30_seconds": sum(gap > 30 for gap in interior_gaps),
            "opportunities_over_60_seconds": sum(gap > 60 for gap in interior_gaps),
        },
        "mean_usd_per_ounce_by_delay": results,
        "tick_sha256": hashes,
    }
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2)
    print(len(trades), results)


if __name__ == "__main__":
    main()

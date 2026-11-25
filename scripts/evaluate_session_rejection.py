"""Evaluate completed-bar previous-session rejection hypotheses."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from train_historical_strategies import BAR, TEST, VALIDATION, samples


def evaluate(path, strategy="rejection"):
    _, bars, start, audit = samples(path)
    previous = bars.groupby(start.dt.normalize()).agg(high=("high", "max"), low=("low", "min")).shift()
    high = start.dt.normalize().map(previous.high)
    low = start.dt.normalize().map(previous.low)
    short = (bars.high > high) & (bars.close < high)
    long = (bars.low < low) & (bars.close > low)
    # Conflicting rejections in the same candle have no directional signal.
    direction = pd.Series(np.select([long & ~short, short & ~long], [1, -1], default=0), index=bars.index)
    if strategy == "breakout":
        true_range = pd.concat([
            bars.high - bars.low,
            (bars.high - bars.close.shift()).abs(),
            (bars.low - bars.close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr = true_range.rolling(16).mean()
        upper = bars.high.shift().rolling(16).max()
        lower = bars.low.shift().rolling(16).min()
        contiguous = start.diff().eq(BAR).rolling(16).sum().eq(16)
        direction = pd.Series(np.select([
            contiguous & (bars.close > upper + .25 * atr),
            contiguous & (bars.close < lower - .25 * atr),
        ], [1, -1], default=0), index=bars.index)
    report = {"sha256": audit.source_sha256, "strategy": strategy, "horizons": {}}
    for horizon in (1, 4, 16):
        # Enter at the next bar open, after the rejection candle completes.
        entry_time = start.shift(-1)
        exit_time = start.shift(-horizon)
        valid = entry_time.eq(start + BAR) & exit_time.eq(start + horizon * BAR)
        gross = direction * (bars.close.shift(-horizon) / bars.open.shift(-1) - 1)
        outcomes = exit_time + BAR
        periods = {
            "train": outcomes < VALIDATION,
            "validation": (entry_time >= VALIDATION) & (outcomes < TEST),
            "test": entry_time >= TEST,
        }
        results = {}
        for name, mask in periods.items():
            eligible = mask & valid & direction.ne(0) & gross.notna()
            trades = gross[eligible]
            accepted = []
            available = pd.Timestamp.min
            for index in bars.index[eligible]:
                if entry_time[index] >= available:
                    accepted.append(index)
                    available = outcomes[index]
            sequential = gross.loc[accepted]
            week = entry_time.loc[accepted].dt.to_period("W-SUN")
            weekly = sequential.groupby(week).agg(["sum", "count"])
            interval = None
            if len(weekly) > 1:
                rng = np.random.default_rng(42)
                draws = rng.integers(len(weekly), size=(2000, len(weekly)))
                mean = weekly["sum"].to_numpy()[draws].sum(axis=1)
                count = weekly["count"].to_numpy()[draws].sum(axis=1)
                interval = (np.quantile(mean / count, [.025, .975]) * 10000).tolist()
            equity = pd.Series(np.r_[1., (1 + sequential).cumprod().to_numpy()])
            results[name] = {
                "weekly_bootstrap_gross_mean_bps_95": interval,
                "gross_max_drawdown": float((equity / equity.cummax() - 1).min()),

                "trade_ledger": [
                    {
                        "signal_time": str(start[index] + BAR),
                        "entry_time": str(entry_time[index]),
                        "exit_time": str(outcomes[index]),
                        "direction": int(direction[index]),
                        "entry_bid_open": float(bars.open.shift(-1)[index]),
                        "exit_bid_close": float(bars.close.shift(-horizon)[index]),
                        "gross_return": float(gross[index]),
                    } for index in accepted
                ],
                "monthly": {
                    str(month): {
                        "trades": len(group),
                        "gross_mean_bps": float(group.mean() * 10000),
                    }
                    for month, group in sequential.groupby(entry_time.loc[accepted].dt.to_period("M"))
                },
                "cost_sensitivity": {
                    str(cost): {
                        "net_mean_bps": float(sequential.mean() * 10000 - cost) if len(sequential) else None,
                        "net_compounded_return": float((1 + sequential - cost / 10000).prod() - 1),
                        "positive_fraction": float((sequential > cost / 10000).mean()) if len(sequential) else None,
                    } for cost in (0, 0.5, 1, 2, 5)
                },
                "sequential_trades": len(sequential),
                "sequential_gross_mean_bps": float(sequential.mean() * 10000) if len(sequential) else None,
                "sequential_compounded_return": float((1 + sequential).prod() - 1),

                "signals": len(trades),
                "gross_mean_bps": float(trades.mean() * 10000) if len(trades) else None,
                "positive_fraction": float((trades > 0).mean()) if len(trades) else None,
            }
        report["horizons"][str(horizon)] = results
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=("rejection", "breakout"), default="rejection")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("feeds", type=Path, nargs="+")
    args = parser.parse_args()
    report = {
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "parameters": {"strategy": args.strategy, "lookback_bars": 16, "atr_buffer": 0.25}
                      if args.strategy == "breakout" else {"strategy": args.strategy},
        "assumptions": [
            "Sessions use broker-native calendar days pending historical UTC mapping",
            "Next-bar open entry and horizon close exit",
            "Gross diagnostic excludes spread, commission and slippage",
            "Sequential results admit one position at a time and reinvest gross returns",
            "All-signal results include overlapping outcomes",
            "Cost sensitivity uses hypothetical round-trip basis points per executed trade",
            "Test period previously inspected and exploratory",
        ],
        "feeds": {path.name: evaluate(path, args.strategy) for path in args.feeds},
    }
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()

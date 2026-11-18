"""Weekly block bootstrap for sequential classifier research trades."""
import argparse
import json

import numpy as np
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("output")
    args = parser.parse_args()
    with open(args.input) as stream:
        report = json.load(stream)
    results = {"no_trade_benchmark": {"trades": 0, "net_return": 0, "drawdown": 0},
               "cost_bps_per_trade": 2, "bootstrap_draws": 2000,
               "limitations": ["Marginal intervals without multiple-testing adjustment",
                               "Exploratory interval, hypothetical costs"], "feeds": {}}
    for feed, horizons in report["feeds"].items():
        feed_results = {}
        for horizon, models in horizons.items():
            summaries = {}
            for name, model in models.items():
                ledger = pd.DataFrame(model["ledger"])
                if ledger.empty:
                    summaries[name] = {"trades": 0}
                    continue
                week = pd.to_datetime(ledger.entry_time).dt.to_period("W-SUN")
                net = ledger.gross_return * 10000 - 2
                weekly = net.groupby(week).agg(["sum", "count"])
                rng = np.random.default_rng(42)
                draws = rng.integers(len(weekly), size=(2000, len(weekly)))
                values = weekly["sum"].to_numpy()[draws].sum(axis=1)
                counts = weekly["count"].to_numpy()[draws].sum(axis=1)
                interval = np.quantile(values / counts, [.025, .975])
                equity = pd.Series(np.r_[1., (1 + net.to_numpy() / 10000).cumprod()])
                summaries[name] = {
                    "trades": len(ledger), "weeks": len(weekly),
                    "net_mean_bps": float(net.mean()),
                    "mean_above_no_trade": bool(net.mean() > 0),
                    "marginal_lower_bound_above_zero": bool(interval[0] > 0) if len(weekly) >= 8 else None,
                    "weekly_bootstrap_95_bps": interval.tolist() if len(weekly) >= 8 else None,
                    "uncertainty_status": "estimated" if len(weekly) >= 8 else "fewer_than_eight_weeks",
                    "trade_close_max_drawdown": float((equity / equity.cummax() - 1).min()),
                }
            feed_results[horizon] = summaries
        results["feeds"][feed] = feed_results
    with open(args.output, "x") as stream:
        json.dump(results, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()

"""Replay saved directional models with next-open entries and one position."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from lightgbm import Booster
from train_historical_strategies import BAR, samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed")
    parser.add_argument("--evaluation-csv", type=Path)
    parser.add_argument("--evaluation-start", type=pd.Timestamp)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.evaluation_csv and not args.feed:
        parser.error("--evaluation-csv requires --feed")
    report = json.loads((args.root / "report.json").read_text())
    results = {"entry": "next bar Bid open", "exit": "horizon Bid close",
               "limitations": ["Hypothetical costs", "Native broker chronology",
                               "Previously inspected test period"], "feeds": {}}
    for feed, config in report["feeds"].items():
        if args.feed and feed != args.feed:
            continue
        features, bars, start, audit = samples(args.evaluation_csv or Path("data/raw/mt5") / feed)
        if not args.evaluation_csv and audit.source_sha256 != config["source_sha256"]:
            raise ValueError("Historical feed fingerprint mismatch")
        feed_results = {}
        for horizon, settings in config["horizons"].items():
            horizon = int(horizon)
            decision = features.decision_server_time
            entry = start.shift(-1)
            exit_time = start.shift(-horizon) + BAR
            valid = features[config["features"]].notna().all(axis=1)
            valid &= entry.eq(decision) & exit_time.eq(decision + horizon * BAR)
            valid &= decision >= (args.evaluation_start or pd.Timestamp(report["test_start"]))
            x = features.loc[valid, config["features"]]
            entry_price = bars.open.shift(-1)
            exit_price = bars.close.shift(-horizon)
            model_results = {}
            probabilities = {}
            for name, suffix in (("LightGBM", "lightgbm.txt"), ("CatBoost", "catboost.cbm"),
                                 ("meta_gate", "meta-gate.txt"), ("ensemble", None), ("regime_gate", None)):
                if name == "regime_gate":
                    gate = settings["regime_gate"]
                    high = x.volatility.to_numpy() > gate["training_volatility_boundary"]
                    choices = gate["validation_selected_models"]
                    probability = np.where(high, probabilities[choices["high"]], probabilities[choices["low"]])
                elif name == "ensemble":
                    probability = (probabilities["LightGBM"] + probabilities["CatBoost"]) / 2
                else:
                    path = args.root / Path(feed).stem / f"{horizon}-{suffix}"
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    if digest != report["model_sha256"][str(path.relative_to(args.root))]:
                        raise ValueError("Saved classifier fingerprint mismatch")
                    if name in ("LightGBM", "meta_gate"):
                        probability = Booster(model_file=str(path)).predict(x)
                    else:
                        model = CatBoostClassifier()
                        model.load_model(str(path))
                        probability = model.predict_proba(x)[:, 1]
                probabilities[name] = probability
                if name == "meta_gate":
                    threshold = settings["meta_gate"]["threshold"]
                    selected = probability >= threshold
                    direction = np.where(x.return_1 <= 0, 1, -1)
                else:
                    threshold = .5 if name == "regime_gate" else settings["direction"][name]["threshold"]
                    selected = np.maximum(probability, 1 - probability) >= threshold
                    direction = np.where(probability > .5, 1, -1)
                available = pd.Timestamp.min
                ledger = []
                for index, sign, use in zip(x.index, direction, selected, strict=True):
                    if use and entry[index] >= available:
                        underlying = exit_price[index] / entry_price[index] - 1
                        gross = sign * underlying
                        ledger.append({"entry_time": str(entry[index]), "exit_time": str(exit_time[index]),
                                       "direction": int(sign), "underlying_return": float(underlying),
                                       "gross_return": float(gross)})
                        available = exit_time[index]
                returns = np.array([trade["gross_return"] for trade in ledger])
                underlying = np.array([trade["underlying_return"] for trade in ledger])
                model_results[name] = {
                    "matched_always_long_net_2bps": float(underlying.mean() * 10000 - 2) if len(returns) else None,
                    "matched_always_short_net_2bps": float(-underlying.mean() * 10000 - 2) if len(returns) else None,
                    "threshold": threshold,
                    "threshold_source": "fixed_direction_cutoff" if name == "regime_gate" else "validation",
                    "trades": len(ledger),
                    "gross_mean_bps": float(returns.mean() * 10000) if len(returns) else None,
                    "hypothetical_2bps_net_mean": float(returns.mean() * 10000 - 2) if len(returns) else None,
                    "ledger": ledger,
                }
            feed_results[str(horizon)] = model_results
        results["feeds"][feed] = feed_results
        results.setdefault("data_lineage", {})[feed] = {
            "training_sha256": config["source_sha256"],
            "evaluation_sha256": audit.source_sha256,
            "evaluation_start": str(args.evaluation_start or report["test_start"]),
        }
    with args.output.open("x") as stream:
        json.dump(results, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()

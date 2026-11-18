"""Fit validation-only additive interval corrections for saved quantile models."""
import argparse
import json
from pathlib import Path

import numpy as np
from lightgbm import Booster
from train_historical_strategies import BAR, TEST, VALIDATION, samples


def calibrate(root):
    report = json.loads((root / "report.json").read_text())
    output = {"target_coverage": .8, "feeds": {},
              "limitation": "Temporal dependence and distribution shift prevent an exchangeability guarantee"}
    for feed, config in report["feeds"].items():
        features, bars, start, _ = samples(Path("data/raw/mt5") / feed)
        results = {}
        for horizon in (1, 4, 16):
            outcome = start.shift(-horizon) + BAR
            decision = features.decision_server_time
            valid = features[config["features"]].notna().all(axis=1) & outcome.eq(decision + horizon * BAR)
            validation = valid & (decision >= VALIDATION) & (outcome < TEST)
            test = valid & (decision >= TEST)
            models = [Booster(model_file=str(root / Path(feed).stem / f"{horizon}-quantile-{q}.txt"))
                      for q in (.1, .5, .9)]
            returns = bars.close.shift(-horizon) / bars.close - 1

            def intervals(mask):
                x = features.loc[mask, config["features"]]
                return np.sort(np.column_stack([model.predict(x) for model in models]), axis=1)

            val = intervals(validation)
            y_val = returns[validation].to_numpy()
            scores = np.maximum(val[:, 0] - y_val, y_val - val[:, 2])
            level = min(1., np.ceil((len(scores) + 1) * .8) / len(scores))
            correction = max(0., float(np.quantile(scores, level, method="higher")))
            pred = intervals(test)
            y = returns[test].to_numpy()
            results[str(horizon)] = {
                "validation_rows": len(scores), "test_rows": len(y),
                "additive_correction_return": correction,
                "raw_sorted_coverage": float(((y >= pred[:, 0]) & (y <= pred[:, 2])).mean()),
                "calibrated_coverage": float(((y >= pred[:, 0] - correction) & (y <= pred[:, 2] + correction)).mean()),
                "calibrated_width_bps": float((pred[:, 2] - pred[:, 0] + 2 * correction).mean() * 10000),
            }
        output["feeds"][feed] = results
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with args.output.open("x") as stream:
        json.dump(calibrate(args.root), stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()

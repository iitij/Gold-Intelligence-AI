"""Produce calibrated probabilities from a saved historical classifier."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from lightgbm import Booster
from train_historical_strategies import samples


def predict(root, feed, horizon, model_name, input_path, as_of=None):
    report = json.loads((root / "report.json").read_text())
    config = report["feeds"][feed]
    settings = config["horizons"][str(horizon)]
    folder = root / Path(feed).stem
    suffix = "lightgbm.txt" if model_name == "LightGBM" else "catboost.cbm"
    path = folder / f"{horizon}-{suffix}"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != report["model_sha256"][str(path.relative_to(root))]:
        raise ValueError("Saved model fingerprint mismatch")
    features, _, _, _ = samples(input_path, as_of=as_of)
    eligible = features.dropna(subset=config["features"])
    if eligible.empty:
        raise ValueError("No eligible completed feature row")
    row = eligible.iloc[[-1]]
    x = row[config["features"]]
    if model_name == "LightGBM":
        model = Booster(model_file=str(path))
        if model.feature_name() != config["features"]:
            raise ValueError("Feature order mismatch")
        probability = float(model.predict(x)[0])
    else:
        model = CatBoostClassifier()
        model.load_model(str(path))
        if model.feature_names_ != config["features"]:
            raise ValueError("Feature order mismatch")
        probability = float(model.predict_proba(x)[0, 1])
    calibration = settings["calibration"][model_name]
    score = calibration["coefficient"] * probability + calibration["intercept"]
    return {
        "decision_server_time": str(row.decision_server_time.iloc[0]),
        "as_of_server_time": str(pd.Timestamp(as_of)) if as_of is not None else None,
        "feature_age_seconds": float(
            (pd.Timestamp(as_of) - row.decision_server_time.iloc[0]).total_seconds()
        ) if as_of is not None else None,
        "model": model_name, "horizon_bars": horizon,
        "raw_up_probability": probability,
        "calibrated_up_probability": float(1 / (1 + np.exp(-score))),
        "model_sha256": digest,
        "status": "historical_research",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", required=True, help="Decision time in native broker chronology")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--feed", required=True)
    parser.add_argument("--horizon", type=int, choices=(1, 4, 16), required=True)
    parser.add_argument("--model", choices=("LightGBM", "CatBoost"), required=True)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    print(json.dumps(predict(args.root, args.feed, args.horizon, args.model, args.input, args.as_of)))


if __name__ == "__main__":
    main()

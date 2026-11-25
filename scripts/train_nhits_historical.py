"""Train CPU NHITS and evaluate the last 16 bars of each held-out segment."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import pandas as pd
import torch
from neuralforecast import NeuralForecast
from neuralforecast.models import NHITS


def evaluate(model, frame):
    context = frame.groupby("unique_id", group_keys=False).head(-16)
    actual = frame.groupby("unique_id", group_keys=False).tail(16)
    predicted = model.predict(df=context[["unique_id", "ds", "y"]])
    joined = actual.merge(predicted, on=["unique_id", "ds"], validate="one_to_one")
    if len(joined) != len(actual) or len(predicted) != len(actual):
        raise ValueError("Forecast boundaries do not match held-out outcomes")
    last = context.groupby("unique_id").y.last()
    baseline = joined.unique_id.map(last)
    return {
        "rows": len(joined),
        "segments": joined.unique_id.nunique(),
        "mae_price": float((joined.NHITS - joined.y).abs().mean()),
        "persistence_mae_price": float((baseline - joined.y).abs().mean()),
        "direction_accuracy": float(((joined.NHITS > baseline) == (joined.y > baseline)).mean()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=200)
    args = parser.parse_args()
    if args.steps < 1:
        parser.error("--steps must be positive")
    args.output.mkdir()
    torch.set_num_threads(2)
    report = {
        "steps": args.steps, "context": 64, "horizon": 16,
        "evaluation": "Last sixteen outcomes per contiguous held-out segment",
        "limitations": ["Exploratory interval previously inspected", "Price forecast metrics exclude execution costs"],
        "versions": {name: importlib.metadata.version(name) for name in ("torch", "neuralforecast")},
        "feeds": {},
    }
    for path in sorted(args.panel.glob("*.csv")):
        frame = pd.read_csv(path, parse_dates=["ds"])
        training = frame.loc[frame.split.eq("train"), ["unique_id", "ds", "y"]]
        model = NeuralForecast(models=[NHITS(
            h=16, input_size=64, max_steps=args.steps, scaler_type="standard",
            random_seed=42, accelerator="cpu", devices=1,
            enable_progress_bar=False, logger=False, enable_checkpointing=False,
        )], freq="15min")
        model.fit(df=training)
        report["feeds"][path.name] = {
            "panel_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "training_rows": len(training),
            "validation": evaluate(model, frame.loc[frame.split.eq("validation")]),
            "test": evaluate(model, frame.loc[frame.split.eq("test")]),
        }
        model.save(path=str(args.output / path.stem), overwrite=False, save_dataset=False)
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()

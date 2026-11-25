"""Evaluate local Chronos-2 on held-out contiguous XAUUSD segments."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
import torch
from chronos import Chronos2Pipeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    weights = args.model / "model.safetensors"
    digest = hashlib.sha256(weights.read_bytes()).hexdigest()
    expected = "ddcda3c7508bf2528087723e98a20707cc04b7f370ae275a9fd88078ddba4f42"
    if weights.stat().st_size != 477930472 or digest != expected:
        raise ValueError("Chronos-2 weights differ from the pinned revision")
    args.output.mkdir()
    torch.set_num_threads(2)
    pipeline = Chronos2Pipeline.from_pretrained(str(args.model), device_map="cpu")
    report = {
        "revision": "29ec3766d36d6f73f0696f85560a422f50e8498c",
        "weights_sha256": digest,
        "mode": "zero-shot", "horizon": 16, "context_bars": 64, "feeds": {},
        "limitations": ["Previously inspected exploratory interval", "Execution costs excluded",
                        "Foundation pretraining overlap with evaluation dates is unverified"],
    }
    for path in sorted(args.panel.glob("*.csv")):
        frame = pd.read_csv(path, parse_dates=["ds"])
        scores = {}
        for split in ("validation", "test"):
            held = frame.loc[frame.split.eq(split)]
            context = held.groupby("unique_id", group_keys=False).head(-16)
            context = context.groupby("unique_id", group_keys=False).tail(64)
            actual = held.groupby("unique_id", group_keys=False).tail(16)
            forecasts = pipeline.predict_df(
                context[["unique_id", "ds", "y"]],
                prediction_length=16, quantile_levels=[.1, .5, .9],
                id_column="unique_id", timestamp_column="ds", target="y",
                context_length=64, cross_learning=False, freq="15min",
            )
            forecasts.to_csv(args.output / f"{path.stem}-{split}-predictions.csv", index=False)
            joined = actual.merge(forecasts, on=["unique_id", "ds"], validate="one_to_one")
            if len(joined) != len(actual) or len(forecasts) != len(actual):
                raise ValueError("Forecast and outcome boundaries differ")
            baseline = joined.unique_id.map(context.groupby("unique_id").y.last())
            scores[split] = {
                "rows": len(joined),
                "mae_price": float((joined["0.5"] - joined.y).abs().mean()),
                "persistence_mae_price": float((baseline - joined.y).abs().mean()),
                "interval_coverage": float(((joined.y >= joined["0.1"]) & (joined.y <= joined["0.9"])).mean()),
            }
        report["feeds"][path.name] = scores
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()

"""Fit fixed CPU baselines for next-bar direction in native server chronology."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
from sklearn.dummy import DummyClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score

from goldintel.data.mt5_csv import validate_mt5_csv

BAR = pd.Timedelta(minutes=15)
FEATURES = ["return_1", "return_4", "range", "body", "tick_volume"]
CUTOFF = pd.Timestamp("2026-04-01")


def prepare(path):
    audit = validate_mt5_csv(path, expected_symbol="XAUUSD")
    bars = pd.read_csv(path)
    start = pd.to_datetime(bars.server_time, format="%Y.%m.%d %H:%M:%S")
    decision = start + BAR
    outcome = start.shift(-1) + BAR
    # Require five contiguous completed input bars and one contiguous label bar.
    contiguous = start.diff().eq(BAR).rolling(4).sum().eq(4)
    eligible = contiguous & outcome.eq(decision + BAR)
    samples = pd.DataFrame({
        "decision_server_time": decision,
        "outcome_server_time": outcome,
        "return_1": bars.close / bars.close.shift(1) - 1,
        "return_4": bars.close / bars.close.shift(4) - 1,
        "range": (bars.high - bars.low) / bars.open,
        "body": bars.close / bars.open - 1,
        "tick_volume": bars.tick_volume,
        "up": (bars.close.shift(-1) > bars.close).astype(int),
    }).loc[eligible].copy()
    samples["split"] = "excluded"
    samples.loc[samples.outcome_server_time < CUTOFF, "split"] = "train"
    samples.loc[samples.decision_server_time >= CUTOFF, "split"] = "test"
    return samples, audit


def evaluate(samples):
    train = samples.loc[samples.split.eq("train")]
    test = samples.loc[samples.split.eq("test")]
    if train.up.nunique() != 2 or test.up.nunique() != 2:
        raise ValueError("Both splits must contain both label classes")
    models = {
        "majority": DummyClassifier(strategy="most_frequent"),
        "LightGBM": LGBMClassifier(n_estimators=100, random_state=42, n_jobs=2, verbosity=-1),
        "CatBoost": CatBoostClassifier(
            iterations=100, depth=5, random_seed=42, thread_count=2,
            verbose=False, allow_writing_files=False,
        ),
    }
    scores = {}
    baseline = None
    for name, model in models.items():
        model.fit(train[FEATURES], train.up)
        predicted = model.predict(test[FEATURES])
        if baseline is None:
            baseline = predicted
        scores[name] = {
            "accuracy": accuracy_score(test.up, predicted),
            "balanced_accuracy": balanced_accuracy_score(test.up, predicted),
        }
        scores[name].update(robustness(test, predicted, baseline))
    persistence = (test.return_1 > 0).astype(int).to_numpy()
    for name, predicted in (("persistence", persistence), ("reversal", 1 - persistence)):
        scores[name] = {
            "accuracy": accuracy_score(test.up, predicted),
            "balanced_accuracy": balanced_accuracy_score(test.up, predicted),
            **robustness(test, predicted, baseline),
        }
    return scores


def robustness(test, predicted, baseline):
    """Resample whole server weeks and compare paired predictions."""
    frame = pd.DataFrame({
        "time": test.decision_server_time,
        "label": test.up,
        "correct": predicted == test.up.to_numpy(),
        "baseline_correct": baseline == test.up.to_numpy(),
    })
    weeks = frame.time.dt.to_period("W-SUN")
    labels = frame.label.to_numpy()
    counts = pd.crosstab(weeks, labels).reindex(columns=[0, 1]).to_numpy()
    differences = (
        frame.assign(delta=frame.correct.astype(int) - frame.baseline_correct.astype(int))
        .groupby([weeks, "label"]).delta.sum().unstack(fill_value=0)
        .reindex(columns=[0, 1]).to_numpy()
    )
    rng = np.random.default_rng(42)
    draws = rng.integers(len(counts), size=(2000, len(counts)))
    denominators = counts[draws].sum(axis=1)
    valid = (denominators > 0).all(axis=1)
    lift = (differences[draws[valid]].sum(axis=1) / denominators[valid]).mean(axis=1)
    monthly = {}
    for month, group in frame.groupby(frame.time.dt.to_period("M")):
        if group.label.nunique() == 2:
            monthly[str(month)] = {
                "rows": len(group),
                "balanced_accuracy": group.groupby("label").correct.mean().mean(),
            }
    return {
        "server_weeks": len(counts),
        "paired_balanced_accuracy_lift_ci95": np.quantile(lift, [0.025, 0.975]).tolist(),
        "monthly": monthly,
    }


def walk_forward(samples):
    """Evaluate fixed models on successive months before the original cutoff."""
    folds = {}
    for start in pd.date_range("2025-04-01", CUTOFF, freq="MS", inclusive="left"):
        end = start + pd.offsets.MonthBegin()
        train = samples.outcome_server_time < start
        test = (samples.decision_server_time >= start) & (samples.outcome_server_time < end)
        fold = samples.loc[train | test].copy()
        fold["split"] = np.where(train.loc[fold.index], "train", "test")
        scores = evaluate(fold)
        folds[str(start.date())] = {
            "train_rows": int(train.sum()),
            "test_rows": int(test.sum()),
            "balanced_accuracy": {
                name: score["balanced_accuracy"] for name, score in scores.items()
            },
        }
    names = next(iter(folds.values()))["balanced_accuracy"]
    return {
        "folds": folds,
        "mean_monthly_balanced_accuracy": {
            name: float(np.mean([fold["balanced_accuracy"][name] for fold in folds.values()]))
            for name in names
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metaquotes", type=Path)
    parser.add_argument("headway", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--walk-forward", action="store_true")
    args = parser.parse_args()
    results = {
        "purpose": "exploratory_next_m15_close_direction",
        "time_basis": "native_server_time_per_feed",
        "utc_verified": False,
        "feature_availability": "assumed available at bar close",
        "cost_model": None,
        "label": "next close strictly above decision bar close",
        "features": FEATURES,
        "test_start_server_time": CUTOFF.isoformat(),
        "feeds": {},
    }
    prepared = {}
    for name in ("metaquotes", "headway"):
        samples, audit = prepare(getattr(args, name))
        prepared[name] = samples
        results["feeds"][name] = {
            "audit": asdict(audit),
            "counts": {str(k): int(v) for k, v in samples.split.value_counts().items()},
            "excluded_noncontiguous_or_boundary_rows": audit.rows - len(samples),
            "scores": evaluate(samples),
        }
        if args.walk_forward:
            results["feeds"][name]["walk_forward"] = walk_forward(samples)
    args.output.mkdir(parents=True, exist_ok=False)
    for name, samples in prepared.items():
        samples.to_csv(args.output / f"{name}-samples.csv", index=False)
    (args.output / "report.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()

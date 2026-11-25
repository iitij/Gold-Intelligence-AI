"""Train and score historical XAUUSD strategies independently on each feed."""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier, LGBMRegressor
from research_m15_direction import BAR
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, brier_score_loss, mean_pinball_loss

from goldintel.data.mt5_csv import validate_mt5_csv

VALIDATION = pd.Timestamp("2026-01-01")
TEST = pd.Timestamp("2026-04-01")


def samples(path, as_of=None):
    audit = validate_mt5_csv(path, expected_symbol="XAUUSD")
    bars = pd.read_csv(path)
    start = pd.to_datetime(bars.server_time, format="%Y.%m.%d %H:%M:%S")
    if as_of is not None:
        completed = start + BAR <= pd.Timestamp(as_of)
        bars = bars.loc[completed].copy()
        start = start.loc[completed]
    close = bars.close
    features = pd.DataFrame({
        "decision_server_time": start + BAR,
        "return_1": close / close.shift(1) - 1,
        "return_4": close / close.shift(4) - 1,
        "range": (bars.high - bars.low) / bars.open,
        "body": close / bars.open - 1,
        "tick_volume": bars.tick_volume,
    })
    features["volatility"] = close.pct_change().rolling(16).std()
    features["trend"] = close / close.shift(16) - 1
    hour = features.decision_server_time.dt.hour
    features["hour_sin"] = np.sin(hour * np.pi / 12)
    features["hour_cos"] = np.cos(hour * np.pi / 12)
    previous = bars.groupby(start.dt.normalize()).agg(high=("high", "max"), low=("low", "min")).shift()
    features["previous_high_distance"] = (bars.high - start.dt.normalize().map(previous.high)) / close
    features["previous_low_distance"] = (bars.low - start.dt.normalize().map(previous.low)) / close
    features.loc[~start.diff().eq(BAR).rolling(16).sum().eq(16), "trend"] = np.nan
    return features, bars, start, audit


def evaluate(path, output):
    features, bars, start, audit = samples(path)
    columns = list(features.columns.drop("decision_server_time"))
    report = {"source_sha256": audit.source_sha256, "features": columns, "horizons": {}}
    for horizon in (1, 4, 16):
        future = start.shift(-horizon)
        outcome = future + BAR
        decision = features.decision_server_time
        eligible = features[columns].notna().all(axis=1) & outcome.eq(decision + horizon * BAR)
        returns = bars.close.shift(-horizon) / bars.close - 1
        train = eligible & (outcome < VALIDATION)
        validation = eligible & (decision >= VALIDATION) & (outcome < TEST)
        test = eligible & (decision >= TEST)
        x_train, x_val, x_test = (features.loc[mask, columns] for mask in (train, validation, test))
        y_train, y_val, y_test = ((returns.loc[mask] > 0).astype(int) for mask in (train, validation, test))
        models = {
            "LightGBM": LGBMClassifier(n_estimators=125, n_jobs=2, random_state=42, verbosity=-1),
            "CatBoost": CatBoostClassifier(iterations=125, depth=5, thread_count=2, random_seed=42, verbose=False, allow_writing_files=False),
        }
        probabilities = {}
        tuning = {}
        for name, model in models.items():
            candidates = []
            for depth in (3, 5, 7):
                if name == "LightGBM":
                    candidate = LGBMClassifier(
                        n_estimators=125, max_depth=depth, num_leaves=2 ** depth,
                        n_jobs=2, random_state=42, verbosity=-1,
                    )
                else:
                    candidate = CatBoostClassifier(
                        iterations=125, depth=depth, thread_count=2,
                        random_seed=42, verbose=False, allow_writing_files=False,
                    )
                candidate.fit(x_train, y_train)
                score = brier_score_loss(y_val, candidate.predict_proba(x_val)[:, 1])
                candidates.append((score, depth, candidate))
            score, depth, model = min(candidates, key=lambda item: item[0])
            tuning[name] = {
                "selected_depth": depth,
                "validation_brier": score,
                "candidates": [{"depth": d, "validation_brier": s} for s, d, _ in candidates],
            }
            probabilities[name] = (model.predict_proba(x_val)[:, 1], model.predict_proba(x_test)[:, 1])
            if name == "LightGBM":
                model.booster_.save_model(str(output / f"{horizon}-lightgbm.txt"))
            else:
                model.save_model(str(output / f"{horizon}-catboost.cbm"))
        probabilities["ensemble"] = tuple(np.mean(parts, axis=0) for parts in zip(*probabilities.values()))
        volatility_boundary = float(x_train.volatility.median())
        validation_high = x_val.volatility.to_numpy() > volatility_boundary
        test_high = x_test.volatility.to_numpy() > volatility_boundary
        gated = np.empty(len(y_test))
        choices = {}
        for high in (False, True):
            val_mask = validation_high == high
            test_mask = test_high == high
            selected_name = min(
                ("LightGBM", "CatBoost", "ensemble"),
                key=lambda name: brier_score_loss(y_val[val_mask], probabilities[name][0][val_mask]),
            )
            gated[test_mask] = probabilities[selected_name][1][test_mask]
            choices["high" if high else "low"] = selected_name
        regime_result = {
            "training_volatility_boundary": volatility_boundary,
            "validation_selected_models": choices,
            "test_brier": brier_score_loss(y_test, gated),
            "test_balanced_accuracy": balanced_accuracy_score(y_test, gated > .5),
        }
        calibration = {}
        for name in ("LightGBM", "CatBoost", "ensemble"):
            val, pred = probabilities[name]
            calibrator = LogisticRegression(random_state=42)
            calibrator.fit(val.reshape(-1, 1), y_val)
            calibrated_test = calibrator.predict_proba(pred.reshape(-1, 1))[:, 1]
            calibration[name] = {
                "coefficient": float(calibrator.coef_[0, 0]),
                "intercept": float(calibrator.intercept_[0]),
                "raw_test_brier": brier_score_loss(y_test, pred),
                "calibrated_test_brier": brier_score_loss(y_test, calibrated_test),
                "calibrated_balanced_accuracy": balanced_accuracy_score(y_test, calibrated_test > .5),
            }
        probabilities["validation_prior"] = (
            np.full(len(y_val), y_val.mean()), np.full(len(y_test), y_val.mean())
        )
        probabilities["prior"] = (np.full(len(y_val), y_train.mean()), np.full(len(y_test), y_train.mean()))
        probabilities["momentum"] = tuple((x.trend > 0).astype(float).to_numpy() for x in (x_val, x_test))
        probabilities["reversal"] = tuple((x.return_1 <= 0).astype(float).to_numpy() for x in (x_val, x_test))
        results = {}
        for name, (val, pred) in probabilities.items():
            results[name] = {
                "balanced_accuracy": balanced_accuracy_score(y_test, pred > .5),
                **({"brier": brier_score_loss(y_test, pred)} if name not in ("momentum", "reversal") else {}),
            }
            if name in ("LightGBM", "CatBoost", "ensemble"):
                threshold = max((.5, .525, .55, .575, .6), key=lambda t: np.where(
                    np.maximum(val, 1 - val) >= t, np.where(val > .5, 1, -1) * returns[validation], 0
                ).mean())
                selected = np.maximum(pred, 1 - pred) >= threshold
                results[name].update(
                    threshold=threshold, coverage=float(selected.mean()),
                    gross_bps_per_opportunity=float(1e4 * np.where(
                        selected, np.where(pred > .5, 1, -1) * returns[test], 0
                    ).mean()),
                )
        base_direction = np.where(features.return_1 <= 0, 1, -1)
        base_return = returns * base_direction
        meta_labels = (base_return > 0).astype(int)
        meta = LGBMClassifier(
            n_estimators=100, max_depth=3, num_leaves=8,
            random_state=42, n_jobs=2, verbosity=-1,
        )
        meta.fit(x_train, meta_labels[train])
        meta.booster_.save_model(str(output / f"{horizon}-meta-gate.txt"))
        meta_validation = meta.predict_proba(x_val)[:, 1]
        meta_test = meta.predict_proba(x_test)[:, 1]
        threshold = max((.5, .525, .55, .575, .6), key=lambda t: np.where(
            meta_validation >= t, base_return[validation], 0
        ).mean())
        chosen = meta_test >= threshold
        meta_result = {
            "base_strategy": "previous_bar_reversal",
            "threshold": threshold,
            "coverage": float(chosen.mean()),
            "test_brier": brier_score_loss(meta_labels[test], meta_test),
            "gross_bps_per_opportunity": float(np.where(chosen, base_return[test], 0).mean() * 10000),
            "base_gross_bps_per_opportunity": float(base_return[test].mean() * 10000),
            "hypothetical_2bps_net_per_opportunity": float(np.where(
                chosen, base_return[test] * 10000 - 2, 0
            ).mean()),
        }
        quantiles = {}
        for alpha in (.1, .5, .9):
            model = LGBMRegressor(objective="quantile", alpha=alpha, n_estimators=125,
                                  random_state=42, n_jobs=2, verbosity=-1)
            model.fit(x_train, returns[train])
            model.booster_.save_model(str(output / f"{horizon}-quantile-{alpha}.txt"))
            quantiles[str(alpha)] = {
                "pinball": mean_pinball_loss(returns[test], model.predict(x_test), alpha=alpha),
                "historical_pinball": mean_pinball_loss(
                    returns[test], np.full(len(x_test), returns[train].quantile(alpha)), alpha=alpha
                ),
            }
        report["horizons"][str(horizon)] = {
            "train_rows": len(x_train), "validation_rows": len(x_val), "test_rows": len(x_test),
            "regime_gate": regime_result, "meta_gate": meta_result, "direction": results, "quantiles": quantiles, "tuning": tuning, "calibration": calibration,
            "split_ranges": {name: {
                "first_decision": str(decision[mask].min()),
                "last_outcome": str(outcome[mask].max()),
            } for name, mask in (("train", train), ("validation", validation), ("test", test))},
        }
    return report


def main():
    global VALIDATION, TEST
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-start", default=str(VALIDATION.date()))
    parser.add_argument("--test-start", default=str(TEST.date()))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("feeds", nargs="+", type=Path)
    args = parser.parse_args()
    VALIDATION = pd.Timestamp(args.validation_start)
    TEST = pd.Timestamp(args.test_start)
    if VALIDATION >= TEST:
        parser.error("--validation-start must precede --test-start")
    args.output.mkdir()
    report = {"validation_start": str(VALIDATION), "test_start": str(TEST), "feeds": {}}
    for path in args.feeds:
        folder = args.output / path.stem
        folder.mkdir()
        report["feeds"][path.name] = evaluate(path, folder)
    report["limitations"] = [
        "Native broker chronology with historical UTC mapping unresolved",
        "Previously inspected test period is exploratory",
        "Gross close-to-close diagnostics exclude spread, fees and slippage",
        "Overlapping signals require portfolio replay",
    ]
    report["versions"] = {name: importlib.metadata.version(name)
                          for name in ("numpy", "pandas", "lightgbm", "catboost", "scikit-learn")}
    report["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report["model_sha256"] = {
        str(path.relative_to(args.output)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(args.output.glob("*/*"))
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()

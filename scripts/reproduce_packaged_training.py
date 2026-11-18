"""Refit frozen validation-selected classifiers from a verified persisted sample package."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from lightgbm import Booster, LGBMClassifier
from prepare_historical_training_set import verify_package
from train_historical_strategies import samples


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--reference-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    total = verify_package(args.package)
    manifest = json.loads((args.package / "manifest.json").read_text())
    reference = json.loads((args.reference_root / "report.json").read_text())
    if (pd.Timestamp(reference["validation_start"]) != pd.Timestamp(manifest["validation_start_native"])
            or pd.Timestamp(reference["test_start"]) != pd.Timestamp(manifest["test_start_native"])):
        raise ValueError("Reference and package split boundaries differ")
    args.output.mkdir(parents=True)
    comparisons = []
    for feed_name, feed in manifest["feeds"].items():
        config = reference["feeds"][feed_name]
        if config["source_sha256"] != feed["source_sha256"]:
            raise ValueError("Package and training source fingerprints differ")
        rebuilt_features, _, _, _ = samples(Path(feed["source"]))
        for horizon, record in feed["horizons"].items():
            columns = record["feature_columns"]
            if columns != config["features"]:
                raise ValueError("Reference feature schema mismatch")
            frames = {}
            for split, info in record["splits"].items():
                x = pd.read_csv(args.package / info["features"], float_precision="round_trip")
                y = pd.read_csv(args.package / info["labels"], float_precision="round_trip")
                if len(x) != config["horizons"][horizon][split + "_rows"]:
                    raise ValueError("Reference sample count mismatch")
                rebuilt = rebuilt_features.loc[y.source_row.to_numpy(), columns].to_numpy()
                if not np.array_equal(x[columns].to_numpy(), rebuilt):
                    raise ValueError("Persisted features differ from the causal source builder")
                frames[split] = (x[columns], y.up_label)
            for name, suffix in (("LightGBM", "lightgbm.txt"), ("CatBoost", "catboost.cbm")):
                relative = f"{Path(feed_name).stem}/{horizon}-{suffix}"
                original_path = args.reference_root / relative
                if digest(original_path) != reference["model_sha256"][relative]:
                    raise ValueError("Reference model fingerprint mismatch")
                depth = config["horizons"][horizon]["tuning"][name]["selected_depth"]
                if name == "LightGBM":
                    model = LGBMClassifier(n_estimators=125, max_depth=depth, num_leaves=2 ** depth,
                                           n_jobs=2, random_state=42, verbosity=-1)
                    original = Booster(model_file=str(original_path))
                else:
                    model = CatBoostClassifier(iterations=125, depth=depth, thread_count=2,
                                                random_seed=42, verbose=False, allow_writing_files=False)
                    original = CatBoostClassifier().load_model(str(original_path))
                model.fit(*frames["train"])
                errors = {}
                for split, (x, _) in frames.items():
                    expected = (original.predict(x, num_threads=2) if name == "LightGBM"
                                else original.predict_proba(x)[:, 1])
                    error = float(np.max(np.abs(model.predict_proba(x)[:, 1] - expected)))
                    if error > 1e-12:
                        raise ValueError(f"Refit probabilities differ on {feed_name}/{horizon}/{name}/{split}")
                    errors[split] = error
                destination = args.output / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                if name == "LightGBM":
                    model.booster_.save_model(str(destination))
                else:
                    model.save_model(str(destination))
                comparisons.append({
                    "feed": feed_name, "horizon": int(horizon), "model": name,
                    "validation_selected_depth": depth, "max_probability_error": errors,
                    "refit_model_sha256": digest(destination),
                    "reference_model_sha256": digest(original_path),
                })
    report = {
        "scope": "Frozen validation-selected direction classifiers refitted from persisted samples",
        "package": str(args.package), "manifest_sha256": digest(args.package / "manifest.json"),
        "reference_report_sha256": digest(args.reference_root / "report.json"),
        "script_sha256": digest(Path(__file__)), "horizon_specific_samples": total,
        "comparisons": comparisons, "approved_for_trading": False,
        "limitations": ["Previously inspected exploratory periods; no new holdout evidence",
                        "Reproduces selected classifiers, not every tuning candidate or other model family",
                        "Gross direction labels, not verified executable outcomes"],
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"PASS: {len(comparisons)} selected classifiers reproduced on all three splits")


if __name__ == "__main__":
    main()

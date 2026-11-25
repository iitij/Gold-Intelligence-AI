"""Materialize exploratory native-clock samples with separate feature and label files."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd
from train_historical_strategies import BAR, samples

SCHEMA = "native-m15-close-direction-v1"
FEATURE_COLUMNS = [
    "return_1", "return_4", "range", "body", "tick_volume", "volatility", "trend",
    "hour_sin", "hour_cos", "previous_high_distance", "previous_low_distance",
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sample_tables(path, horizon, validation_start, test_start):
    features, bars, start, audit = samples(path)
    columns = list(features.columns.drop("decision_server_time"))
    if columns != FEATURE_COLUMNS:
        raise ValueError("Feature builder changed; review and version the sample schema")
    decision = features.decision_server_time
    outcome = start.shift(-horizon) + BAR
    returns = bars.close.shift(-horizon) / bars.close - 1
    complete_features = features[columns].notna().all(axis=1)
    eligible = complete_features & outcome.eq(decision + horizon * BAR)
    masks = {
        "train": eligible & (outcome < validation_start),
        "validation": eligible & (decision >= validation_start) & (outcome < test_start),
        "test": eligible & (decision >= test_start),
    }
    tables = {}
    for split, mask in masks.items():
        ids = [hashlib.sha256(f"{SCHEMA}:{audit.source_sha256}:{horizon}:{index}".encode()).hexdigest()
               for index in features.index[mask]]
        x = features.loc[mask].rename(columns={"decision_server_time": "decision_native"}).copy()
        x.insert(0, "sample_id", ids)
        y = pd.DataFrame({
            "sample_id": ids, "source_row": features.index[mask].to_numpy(),
            "outcome_native": outcome[mask].to_numpy(),
            "forward_return": returns[mask].to_numpy(),
            "up_label": (returns[mask] > 0).astype(int).to_numpy(),
        })
        tables[split] = (x, y)
    counts = {
        "source_rows": len(features), "incomplete_features": int((~complete_features).sum()),
        "unavailable_or_discontinuous_outcomes": int((complete_features & ~eligible).sum()),
        "purged_boundary_samples": int(eligible.sum() - sum(mask.sum() for mask in masks.values())),
        "eligible_before_boundary_purge": int(eligible.sum()),
    }
    return tables, columns, counts, audit.source_sha256


def prepare_package(paths, output, validation_start, test_start):
    validation_start, test_start = pd.Timestamp(validation_start), pd.Timestamp(test_start)
    if (validation_start.tzinfo is not None or test_start.tzinfo is not None
            or validation_start >= test_start):
        raise ValueError("Use increasing naive timestamps in native broker chronology")
    if len({path.name for path in paths}) != len(paths):
        raise ValueError("Input feed names must be distinct")
    source_hashes = [digest(path) for path in paths]
    if len(set(source_hashes)) != len(source_hashes):
        raise ValueError("Duplicate source contents cannot be treated as separate feeds")
    output.mkdir(parents=True)
    manifest = {
        "schema": SCHEMA, "chronology": "native_broker_time_utc_unverified",
        "validation_start_native": str(validation_start), "test_start_native": str(test_start),
        "label": "future_close / decision_close - 1; up iff strictly positive",
        "feature_availability_assumption": "completed native M15 bar available at its nominal close",
        "final_holdout_locked": False, "approved_for_training_or_trading": False,
        "limitations": [
            "Previously inspected evaluation dates are exploratory",
            "Native calendar features do not establish UTC session alignment",
            "Gross close-to-close labels exclude executable spread, commission, latency and slippage",
            "Within-split overlapping outcomes remain dependent; no uniqueness weights applied",
            "Nominal bar completion is not a measured data publication timestamp",
            "Consumers must require and verify the completion manifest before reading samples",
        ],
        "script_sha256": digest(Path(__file__)),
        "feature_builder_sha256": digest(Path(__file__).with_name("train_historical_strategies.py")),
        "versions": {name: importlib.metadata.version(name) for name in ("numpy", "pandas")},
        "feeds": {}, "files": {},
    }
    for path, source_hash in zip(paths, source_hashes):
        feed = {"source": str(path), "source_sha256": source_hash, "horizons": {}}
        for horizon in (1, 4, 16):
            tables, columns, counts, checked_hash = sample_tables(path, horizon, validation_start, test_start)
            if checked_hash != source_hash:
                raise ValueError("Source changed during sample preparation")
            record = {"feature_columns": columns, "exclusions": counts, "splits": {}}
            for split, (x, y) in tables.items():
                if x.empty:
                    raise ValueError(f"Empty {path.name}/{horizon}/{split}")
                folder = output / path.stem / str(horizon) / split
                folder.mkdir(parents=True)
                files = {}
                for kind, frame in (("features", x), ("labels", y)):
                    destination = folder / f"{kind}.csv"
                    frame.to_csv(destination, index=False, float_format="%.17g")
                    relative = str(destination.relative_to(output))
                    manifest["files"][relative] = digest(destination)
                    files[kind] = relative
                record["splits"][split] = {
                    **files, "rows": len(x), "up_labels": int(y.up_label.sum()),
                    "first_decision_native": str(x.decision_native.min()),
                    "last_outcome_native": str(y.outcome_native.max()),
                }
            feed["horizons"][str(horizon)] = record
        manifest["feeds"][path.name] = feed
    # This file is the completion marker. An interrupted build has no usable package.
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    return manifest


def verify_package(output):
    manifest = json.loads((output / "manifest.json").read_text())
    if manifest["schema"] != SCHEMA or manifest["chronology"] != "native_broker_time_utc_unverified":
        raise ValueError("Unsupported sample schema or chronology")
    validation = pd.Timestamp(manifest["validation_start_native"])
    test = pd.Timestamp(manifest["test_start_native"])
    if validation.tzinfo is not None or test.tzinfo is not None or validation >= test:
        raise ValueError("Invalid native split boundaries")
    seen = set()
    referenced = set()
    total = 0
    for feed in manifest["feeds"].values():
        if digest(Path(feed["source"])) != feed["source_sha256"]:
            raise ValueError("Source fingerprint mismatch")
        source = pd.read_csv(feed["source"])
        source_start = pd.to_datetime(source.server_time, format="%Y.%m.%d %H:%M:%S")
        if set(feed["horizons"]) != {"1", "4", "16"}:
            raise ValueError("Missing or unsupported label horizon")
        for horizon, record in feed["horizons"].items():
            if record["feature_columns"] != FEATURE_COLUMNS or set(record["splits"]) != {
                "train", "validation", "test",
            }:
                raise ValueError("Incomplete split set or unsupported feature schema")
            for split, info in record["splits"].items():
                frames = {}
                for kind in ("features", "labels"):
                    relative = info[kind]
                    path = (output / relative).resolve()
                    if not path.is_relative_to(output.resolve()):
                        raise ValueError("Sample path escapes package")
                    if digest(path) != manifest["files"][relative]:
                        raise ValueError("Sample fingerprint mismatch")
                    referenced.add(relative)
                    frames[kind] = pd.read_csv(path, float_precision="round_trip")
                x, y = frames["features"], frames["labels"]
                if list(x.columns) != ["sample_id", "decision_native", *record["feature_columns"]]:
                    raise ValueError("Feature schema mismatch")
                if list(y.columns) != ["sample_id", "source_row", "outcome_native", "forward_return", "up_label"]:
                    raise ValueError("Label schema mismatch")
                if (len(x) != info["rows"] or not len(x) or len(x) != len(y)
                        or not x.sample_id.equals(y.sample_id) or not x.sample_id.is_unique
                        or set(x.sample_id) & seen):
                    raise ValueError("Sample identity, split separation or row-count mismatch")
                seen.update(x.sample_id)
                if (not pd.api.types.is_integer_dtype(y.source_row) or (y.source_row < 0).any()
                        or not y.source_row.is_unique):
                    raise ValueError("Invalid source row provenance")
                expected_ids = [
                    hashlib.sha256(f"{SCHEMA}:{feed['source_sha256']}:{horizon}:{index}".encode()).hexdigest()
                    for index in y.source_row
                ]
                if list(x.sample_id) != expected_ids:
                    raise ValueError("Sample ID does not match source row provenance")
                index = y.source_row.to_numpy()
                if (index + int(horizon) >= len(source)).any():
                    raise ValueError("Sample outcome is outside its source")
                decision = pd.to_datetime(x.decision_native)
                outcome = pd.to_datetime(y.outcome_native)
                if (decision.dt.tz is not None or outcome.dt.tz is not None
                        or not decision.is_monotonic_increasing or not decision.is_unique
                        or not outcome.eq(decision + int(horizon) * BAR).all()):
                    raise ValueError("Invalid native sample chronology")
                valid = {
                    "train": outcome < validation,
                    "validation": (decision >= validation) & (outcome < test),
                    "test": decision >= test,
                }
                if split not in valid or not valid[split].all():
                    raise ValueError("Outcome leaks across a split boundary")
                expected_decision = source_start.iloc[index].reset_index(drop=True) + BAR
                expected_outcome = source_start.iloc[index + int(horizon)].reset_index(drop=True) + BAR
                expected_return = (source.close.iloc[index + int(horizon)].to_numpy()
                                   / source.close.iloc[index].to_numpy() - 1)
                if (not decision.equals(expected_decision) or not outcome.equals(expected_outcome)
                        or not np.array_equal(y.forward_return.to_numpy(), expected_return)):
                    raise ValueError("Labels or timestamps do not match the original source rows")
                if (not np.isfinite(x[record["feature_columns"]].to_numpy()).all()
                        or not np.isfinite(y.forward_return).all()
                        or not y.up_label.eq((y.forward_return > 0).astype(int)).all()
                        or int(y.up_label.sum()) != info["up_labels"]):
                    raise ValueError("Nonfinite features or inconsistent labels")
                total += len(x)
    if referenced != set(manifest["files"]) or not total:
        raise ValueError("Unreferenced files or empty sample package")
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feeds", nargs="*", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validation-start", default="2026-01-01")
    parser.add_argument("--test-start", default="2026-04-01")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if not args.verify_only:
        if not args.feeds:
            parser.error("Supply original feed files")
        prepare_package(args.feeds, args.output, args.validation_start, args.test_start)
    total = verify_package(args.output)
    print(f"PASS: {total} horizon-specific samples verified")


if __name__ == "__main__":
    main()

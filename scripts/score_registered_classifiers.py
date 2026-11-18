"""Score the six registered classifier cases after the entire UTC window closes."""

import argparse
import csv
import hashlib
import importlib.metadata
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from goldintel.research.holdout import assert_holdout_released, read_protocol

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "planning/prospective_holdout_20261118.json"
FEED = "headway_xauusd_m15_20261110.csv"
MODEL_ROOT = "artifacts/historical-strategies-2026-11-17-regime"
LABEL_ROOT = "data/features/native-training-set-v1-20261118"
MODELS = {"LightGBM": "lightgbm.txt", "CatBoost": "catboost.cbm"}
HORIZONS = (1, 4, 16)
BAR = timedelta(minutes=15)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def utc_timestamp(value):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() != timedelta(0) or stamp.minute % 15 or stamp.second or stamp.microsecond:
        raise ValueError("Expected an explicitly UTC, quarter-hour-aligned boundary")
    return stamp


def read_clock_evidence(path, source_sha, first, last, protocol):
    """Verify evidence binding/coverage. Source and review claims require a human audit."""
    record = json.loads(path.read_bytes())
    if (record.get("schema_version") != 1 or record.get("server") != protocol["server"]
            or record.get("symbol") != protocol["symbol"] or record.get("bars_sha256") != source_sha):
        raise ValueError("Clock evidence does not identify these bars and this broker")
    entries = []
    for interval in record["intervals"]:
        a = utc_timestamp(interval["start_utc"])
        b = utc_timestamp(interval["end_exclusive_utc"])
        offset = interval["native_minus_utc_seconds"]
        if a >= b or type(offset) is not int or offset % 900 or abs(offset) > 14 * 3600:
            raise ValueError("Invalid clock evidence interval or offset")
        sources = interval["evidence_sha256"]
        if not isinstance(sources, dict) or not sources:
            raise ValueError("Each clock interval needs evidence files")
        root = path.resolve().parent
        for relative, expected in sources.items():
            source = (root / relative).resolve()
            if not source.is_relative_to(root) or not source.is_file() or digest(source) != expected:
                raise ValueError("Clock evidence file missing or fingerprint mismatch")
        entries.append((a, b, offset))
    entries.sort()
    if (not entries or entries[0][0] > first or entries[-1][1] < last
            or any(a[1] != b[0] for a, b in zip(entries, entries[1:]))):
        raise ValueError("Clock evidence must cover the registered window without a gap or overlap")
    return entries


def check_runtime(frozen):
    locked = {}
    for filename in ("requirements-ci.lock", "requirements-ml-baseline.lock"):
        for name, version in re.findall(r"^([\w.-]+)==([^\s\\]+)", (frozen / filename).read_text(), re.M):
            locked[re.sub(r"[-_.]+", "-", name).lower()] = version
    installed = {re.sub(r"[-_.]+", "-", d.metadata["Name"]).lower(): d.version
                 for d in importlib.metadata.distributions()}
    if not locked or locked != installed:
        raise ValueError("Use a clean environment with the two registered package locks")
    return installed


def frozen_file(protocol, frozen, relative):
    expected = protocol["frozen_files"].get(relative)
    path = frozen / relative
    if expected is None or digest(path) != expected:
        raise ValueError(f"Required file is not verified in the frozen protocol: {relative}")
    return path


def load_priors(protocol, frozen, config):
    priors = {}
    for h in HORIZONS:
        prior = protocol["secondary"]["frozen_validation_priors"][str(h)]
        relative = f"{LABEL_ROOT}/{Path(FEED).stem}/{h}/validation/labels.csv"
        path = frozen_file(protocol, frozen, relative)
        if digest(path) != prior["validation_labels_sha256"]:
            raise ValueError("Frozen validation label fingerprints differ")
        with path.open(newline="", encoding="utf-8") as stream:
            outcomes = [int(row["up_label"]) for row in csv.DictReader(stream)]
        probability = prior["up_probability"]
        if (not outcomes or len(outcomes) != prior["rows"] or set(outcomes) - {0, 1}
                or not 0 <= probability <= 1 or sum(outcomes) / len(outcomes) != probability
                or len(outcomes) != config["horizons"][str(h)]["validation_rows"]):
            raise ValueError("Frozen validation prior doesn't match its outcomes or training report")
        priors[h] = probability
    return priors


def score_frame(features, bars, native_open, entries, start, end, columns, priors, predict):
    """Build one common cohort per horizon and compare model/prior on those outcomes."""
    import numpy as np
    import pandas as pd

    if list(features.columns.drop("decision_server_time")) != columns:
        raise ValueError("Frozen feature schema mismatch")
    open_utc = pd.Series(pd.NaT, index=native_open.index, dtype="datetime64[ns, UTC]")
    for lower, upper, shift in entries:
        candidate_utc = (native_open - timedelta(seconds=shift)).dt.tz_localize("UTC")
        covered = (candidate_utc >= lower) & (candidate_utc + BAR <= upper)
        if (open_utc.notna() & covered).any():
            raise ValueError("Ambiguous native candle mapping; review clock change")
        open_utc.loc[covered] = candidate_utc.loc[covered]
    mapped = open_utc.dropna()
    if mapped.duplicated().any() or not mapped.is_monotonic_increasing:
        raise ValueError("Mapped UTC candle order is invalid")
    decision = open_utc + BAR
    in_window = (decision >= start) & (decision < end)
    complete_features = pd.Series(np.isfinite(features[columns].to_numpy()).all(axis=1),
                                  index=features.index)
    eligible_decisions = pd.date_range(start, end, freq="15min", inclusive="left")
    missing_decisions = eligible_decisions.difference(decision.loc[in_window])
    coverage = {
        "possible_quarter_hours": len(eligible_decisions),
        "present_decision_quarter_hours": int(in_window.sum()),
        "missing_decision_times_utc": [t.isoformat() for t in missing_decisions],
        "missing_includes_unclassified_closures": True,
        "invalid_or_incomplete_features": int((in_window & ~complete_features).sum()),
        "raw_bars_outside_clock_mapping_or_straddling_interval": int(open_utc.isna().sum()),
    }
    results, ledgers = {}, {}
    for h in HORIZONS:
        outcome = decision.shift(-h)
        native_contiguous = features.decision_server_time.shift(-h).eq(features.decision_server_time + h * BAR)
        has_outcome = (outcome < end) & outcome.eq(decision + h * BAR) & native_contiguous
        mask = in_window & complete_features & has_outcome
        y = (bars.close.shift(-h).loc[mask].to_numpy() > bars.close.loc[mask].to_numpy()).astype(int)
        ledger = pd.DataFrame({"decision_utc": decision.loc[mask].map(lambda t: t.isoformat()),
                               "outcome_utc": outcome.loc[mask].map(lambda t: t.isoformat()),
                               "decision_native": features.decision_server_time.loc[mask],
                               "up_label": y})
        result = {"rows": len(y), "positive_labels": int(y.sum()),
                  "feature_eligible_rows_with_unavailable_or_out_of_window_outcomes": int(
                      (in_window & complete_features & ~has_outcome).sum()),
                  "prior": priors[h], "prior_brier": None, "models": {}}
        if len(y):
            x = features.loc[mask, columns]
            prior_score = float(np.square(priors[h] - y).mean())
            result["prior_brier"] = prior_score
            for name in MODELS:
                raw, calibrated = predict(h, name, x)
                if (raw.shape != y.shape or calibrated.shape != y.shape
                        or not np.all((raw >= 0) & (raw <= 1))
                        or not np.all((calibrated >= 0) & (calibrated <= 1))):
                    raise ValueError("Invalid frozen classifier output")
                score = float(np.square(calibrated - y).mean())
                result["models"][name] = {"brier": score, "brier_minus_prior": score - prior_score}
                ledger[f"{name}_raw_up_probability"] = raw
                ledger[f"{name}_calibrated_up_probability"] = calibrated
        else:
            result["models"] = {name: {"brier": None, "brier_minus_prior": None} for name in MODELS}
        results[str(h)], ledgers[str(h)] = result, ledger
    return coverage, results, ledgers


def load_predictor(protocol, frozen, config, report):
    import numpy as np
    from catboost import CatBoostClassifier
    from lightgbm import Booster

    def predict(h, name, x):
        relative = f"{Path(FEED).stem}/{h}-{MODELS[name]}"
        path = frozen_file(protocol, frozen, f"{MODEL_ROOT}/{relative}")
        if digest(path) != report["model_sha256"][relative]:
            raise ValueError("Model is not identified by the frozen training report")
        if name == "LightGBM":
            model = Booster(model_file=str(path))
            if model.feature_name() != config["features"]:
                raise ValueError("Frozen LightGBM feature order differs")
            raw = model.predict(x, num_threads=2)
        else:
            model = CatBoostClassifier().load_model(str(path))
            if model.feature_names_ != config["features"] or list(model.classes_) != [0, 1]:
                raise ValueError("Frozen CatBoost features or classes differ")
            raw = model.predict_proba(x, thread_count=2)[:, 1]
        calibration = config["horizons"][str(h)]["calibration"][name]
        adjusted = calibration["coefficient"] * raw + calibration["intercept"]
        return raw, 1 / (1 + np.exp(-adjusted))

    return predict


def score_verified_input(protocol, frozen, path, entries, start, end):
    report = json.loads(frozen_file(protocol, frozen, f"{MODEL_ROOT}/report.json").read_bytes())
    config = report["feeds"][FEED]
    priors = load_priors(protocol, frozen, config)
    builder = frozen_file(protocol, frozen, "scripts/train_historical_strategies.py").resolve()
    sys.path.insert(0, str(builder.parent))
    from train_historical_strategies import samples

    if Path(sys.modules[samples.__module__].__file__).resolve() != builder:
        raise ValueError("Loaded feature builder differs from the frozen script path")
    common = frozen_file(protocol, frozen, "scripts/research_m15_direction.py").resolve()
    if Path(sys.modules["research_m15_direction"].__file__).resolve() != common:
        raise ValueError("Loaded candle interval differs from the frozen dependency path")
    validator = Path(sys.modules["goldintel.data.mt5_csv"].__file__)
    if digest(validator) != protocol["frozen_files"]["src/goldintel/data/mt5_csv.py"]:
        raise ValueError("Loaded bar validator differs from the frozen dependency bytes")
    features, bars, opens, _ = samples(path)
    return score_frame(features, bars, opens, entries, start, end, config["features"], priors,
                       load_predictor(protocol, frozen, config, report))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bars", type=Path)
    parser.add_argument("--clock-evidence", type=Path, required=True)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    anchor = PROTOCOL.with_suffix(".sha256").read_text().strip()
    protocol = read_protocol(PROTOCOL, anchor)
    first = utc_timestamp(protocol["start_utc"])
    last = utc_timestamp(protocol["end_exclusive_utc"])
    assert_holdout_released(protocol, now=datetime.now(timezone.utc), start=first, end=last,
                            frozen_root=args.frozen_root,
                            replay_path=args.frozen_root / "scripts/replay_m15_reversal.py")
    if (protocol["server"] != "Headway-Demo" or protocol["symbol"] != "XAUUSD"
            or protocol["secondary"]["models"] != list(MODELS)
            or protocol["secondary"]["horizons_M15"] != list(HORIZONS)):
        raise ValueError("Unsupported frozen classifier scope")
    installed = check_runtime(args.frozen_root)
    bars_sha = digest(args.bars)
    clock_sha = digest(args.clock_evidence)
    entries = read_clock_evidence(args.clock_evidence, bars_sha, first, last, protocol)
    coverage, results, ledgers = score_verified_input(protocol, args.frozen_root, args.bars, entries, first, last)
    if bars_sha != digest(args.bars) or clock_sha != digest(args.clock_evidence):
        raise ValueError("Evaluation input changed while reading")
    args.output.mkdir()
    ledgers_sha = {}
    for horizon, ledger in ledgers.items():
        path = args.output / f"horizon-{horizon}-ledger.csv"
        ledger.to_csv(path, index=False)
        ledgers_sha[path.name] = digest(path)
    report = {
        "scope": "descriptive registered classifier comparison",
        "protocol_sha256": anchor, "script_sha256": digest(Path(__file__)), "bars_sha256": bars_sha,
        "clock_evidence_sha256": clock_sha, "start_utc": first.isoformat(), "end_exclusive_utc": last.isoformat(),
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(), "installed_packages": installed,
        "coverage": coverage, "horizons": results, "ledgers_sha256": ledgers_sha,
        "labels": "strictly positive close-to-close movement on contiguous M15 candles",
        "limitations": ["Clock evidence authenticity, session coverage and observed data availability require review",
                        "Bar close is the nominal availability boundary; delivery latency is unverified",
                        "Direction Brier does not measure executable fills or fees",
                        "Six descriptive cases; no model promotion or gate acceptance"],
        "approved_for_trading": False, "complete_holdout_evidence": False,
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print("Completed descriptive scoring for three horizons and two registered classifiers")


if __name__ == "__main__":
    main()

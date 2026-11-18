"""Register a future research window and preserve copies of its code and candidate models."""
import argparse
import csv
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from goldintel.research.holdout import read_protocol, verify_frozen_files
from goldintel.research.point_in_time import _require_utc


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, type=datetime.fromisoformat)
    parser.add_argument("--end", required=True, type=datetime.fromisoformat)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--model-root", required=True, type=Path)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    for key, value in (("start", args.start), ("end", args.end)):
        _require_utc(value, key)
        if value.weekday() != 0 or value.time().isoformat() != "00:00:00":
            parser.error("Use complete Monday-to-Monday UTC weeks")
    if not now < args.start < args.end or args.end - args.start < timedelta(weeks=8):
        parser.error("Register before the start, with at least eight complete weeks")
    if args.protocol.exists() or args.protocol.with_suffix(".sha256").exists() or args.snapshot.exists():
        parser.error("Use fresh protocol and snapshot paths")
    ntp = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized"], check=True,
                         capture_output=True, text=True).stdout.strip()
    if ntp != "NTPSynchronized=yes":
        parser.error("Host clock synchronization is not confirmed")
    model_report = json.loads((args.model_root / "report.json").read_text())
    feed = "headway_xauusd_m15_20261110.csv"
    if digest(Path("data/raw/mt5") / feed) != model_report["feeds"][feed]["source_sha256"]:
        parser.error("Original model training source changed")
    files = [
        Path("requirements-ci.lock"), Path("requirements-ml-baseline.lock"),
        Path("planning/research_run_index.json"), Path("docs/33-REVERSAL-REPLAY.md"),
        Path("scripts/register_prospective_holdout.py"), Path("scripts/replay_m15_reversal.py"),
        Path("scripts/research_m15_direction.py"), Path("scripts/train_historical_strategies.py"),
        Path("scripts/predict_historical_model.py"), Path("scripts/replay_saved_classifiers.py"),
        Path("scripts/export_headway_ticks.py"), Path("scripts/export_headway_bars.py"),
        Path("scripts/export_headway_contract.py"), Path("scripts/observe_headway_clock.py"),
        Path("scripts/normalize_headway_ticks.py"), Path("scripts/summarize_headway_clock.py"),
        Path("artifacts/headway-standard-cost-evidence-20261118.json"),
        Path("data/raw/mt5/headway_xauusd_m15_20261110.csv"),
        args.model_root / "report.json",
    ]
    files.extend(sorted(Path("src/goldintel").rglob("*.py")))
    priors = {}
    for horizon in (1, 4, 16):
        label_path = (Path("data/features/native-training-set-v1-20261118") / Path(feed).stem
                      / str(horizon) / "validation/labels.csv")
        # These outcomes precede the future window and were already inspected.
        with label_path.open(newline="") as stream:
            labels = [int(row["up_label"]) for row in csv.DictReader(stream)]
        priors[str(horizon)] = {"up_probability": sum(labels) / len(labels),
                               "validation_labels_sha256": digest(label_path), "rows": len(labels)}
        files.append(label_path)
        for suffix in ("lightgbm.txt", "catboost.cbm"):
            relative = f"{Path(feed).stem}/{horizon}-{suffix}"
            path = args.model_root / relative
            if digest(path) != model_report["model_sha256"][relative]:
                parser.error("Candidate model hash differs from its training report")
            files.append(path)
    frozen = args.snapshot / "frozen"
    frozen.mkdir(parents=True)
    hashes = {}
    for path in sorted(set(files)):
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Snapshot inputs must be repository-relative")
        target = frozen / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        hashes[str(path)] = digest(target)
        if hashes[str(path)] != digest(path):
            raise ValueError("Snapshot source changed while copying")
    protocol = {
        "schema_version": 1, "kind": "prospective_research_registration",
        "id": args.protocol.stem,
        "registered_at_utc": now.isoformat(), "start_utc": args.start.isoformat(),
        "end_exclusive_utc": args.end.isoformat(), "ntp_at_registration": ntp,
        "server": "Headway-Demo", "symbol": "XAUUSD", "frozen_files": hashes,
        "primary": {
            "strategy": "previous_M15_Bid_close_reversal_including_ties_long",
            "benchmark": "no_trade_zero_return", "position_unit": "one_independent_ounce",
            "metric": "mean_net_USD_per_ounce", "delay_seconds": 0,
            "additional_slippage_per_side_USD_per_ounce": "0",
            "commission": "documented actual account terms for each observed interval; no silent zero default",
            "screen": "positive lower endpoint of paired UTC-week bootstrap 95 percent interval",
            "bootstrap_draws": 2000, "bootstrap_seed": 42, "minimum_populated_weeks": 8,
            "scope": "screening result only; not statistical or production gate acceptance",
        },
        "sensitivity": {"delays_seconds": [0, 1, 5],
                        "additional_slippage_USD_per_side_per_ounce": ["0", "0.05", "0.10", "0.25"]},
        "secondary": {
            "models": ["LightGBM", "CatBoost"], "horizons_M15": [1, 4, 16],
            "metric": "Brier on each frozen calibrated probability versus frozen validation prior",
            "frozen_validation_priors": priors,
            "status": "descriptive six-case comparison; no winner promotion or confirmatory claim",
        },
        "data_conditions": [
            "UTC quote mapping must be evidenced throughout the window, not inferred from one session",
            "Require two warm-up M15 bars and quotes bracketing the end boundary",
            "Preserve raw batch hashes, observed quotes, account terms and cost changes",
            "Report missing quotes and unobservable outcomes; do not silently delete bad periods",
            "Broker session evidence must separate scheduled closures from unobservable tradable quotes",
            "Unresolved eligible-market fills block a positive screening claim",
            "No interim performance evaluation or tuning using any part of this window",
            "Primary executable-cost claim requires documented commission; unresolved costs block acceptance",
        ],
        "limitations": [
            "Local registration and SHA256 snapshots are not independent timestamps or OS access controls",
            "Registry overlap guards protect the repository replay; raw files and other programs remain readable",
            "No future quotes have been collected or evaluated by this registration",
            "Secondary classifier quote execution and publication-delay validation remain separate work",
        ],
        "complete_holdout_evidence": False, "approved_for_trading": False,
    }
    if datetime.now(timezone.utc) >= args.start:
        raise ValueError("Snapshot preparation crossed the evaluation start")
    payload = json.dumps(protocol, indent=2, allow_nan=False) + "\n"
    with args.protocol.open("x") as stream:
        stream.write(payload)
    protocol_hash = digest(args.protocol)
    with args.protocol.with_suffix(".sha256").open("x") as stream:
        stream.write(protocol_hash + "\n")
    shutil.copyfile(args.protocol, args.snapshot / "protocol.json")
    verify_frozen_files(read_protocol(args.protocol, protocol_hash), frozen)
    print(f"REGISTERED: {len(hashes)} frozen files; protocol SHA256 {protocol_hash}")


if __name__ == "__main__":
    main()

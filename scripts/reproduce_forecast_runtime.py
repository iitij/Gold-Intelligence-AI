"""Reproduce saved CPU forecast inference in an exact, hash-installed environment."""
import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
import re
import subprocess
import sys
import time
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_runtime(lock):
    expected = {re.sub(r"[-_.]+", "-", name).lower(): version for name, version in
                re.findall(r"^([\w.-]+)==([^\s\\]+)", lock.read_text(), re.M)}
    installed = {re.sub(r"[-_.]+", "-", dist.metadata["Name"]).lower(): dist.version
                 for dist in importlib.metadata.distributions()}
    if not expected or expected != installed:
        raise ValueError("Installed distribution set must exactly match the supplied lock")
    return installed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--nhits", type=Path, required=True)
    parser.add_argument("--chronos-model", type=Path, required=True)
    parser.add_argument("--chronos-reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    packages = verify_runtime(args.lock)
    original = json.loads((args.nhits / "report.json").read_text())
    models = original.get("model_sha256", {})
    feeds = original["feeds"]
    if not feeds or set(p.name for p in args.panel.glob("*.csv")) != set(feeds):
        raise ValueError("Panel feed set differs from the saved NHITS report")
    expected_models = {f"{Path(feed).stem}/{name}" for feed in feeds
                       for name in ("configuration.json", "NHITS_0.safetensors")}
    if set(models) != expected_models:
        raise ValueError("Saved NHITS report lacks exact model fingerprints")
    for name, expected in models.items():
        if digest(args.nhits / name) != expected:
            raise ValueError("Saved NHITS model fingerprint differs")
    for name, details in feeds.items():
        if digest(args.panel / name) != details["panel_sha256"]:
            raise ValueError("Forecast panel fingerprint differs")
    expected_files = {f"{Path(name).stem}-{split}-predictions.csv"
                      for name in feeds for split in ("validation", "test")}
    if {p.name for p in args.chronos_reference.glob("*-predictions.csv")} != expected_files:
        raise ValueError("Chronos reference prediction set differs")
    if args.output.exists():
        raise ValueError("Output must be a new directory")

    import pandas as pd
    import torch
    from neuralforecast import NeuralForecast
    from train_nhits_historical import evaluate

    torch.set_num_threads(2)
    args.output.mkdir()
    comparisons = []
    for name, details in sorted(feeds.items()):
        frame = pd.read_csv(args.panel / name, parse_dates=["ds"])
        model = NeuralForecast.load(path=str(args.nhits / Path(name).stem))
        for split in ("validation", "test"):
            started = time.perf_counter()
            metrics = evaluate(model, frame.loc[frame.split.eq(split)])
            errors = {key: abs(metrics[key] - details[split][key]) for key in metrics}
            if any(not math.isfinite(value) or value > 1e-6 for value in errors.values()):
                raise ValueError("Reloaded NHITS metrics differ from the saved reference")
            comparisons.append({"model": "NHITS", "feed": name, "split": split,
                                "inference_wall_seconds": time.perf_counter() - started,
                                "absolute_metric_errors": errors})
    chronos_output = args.output / "chronos"
    started = time.perf_counter()
    subprocess.run([
        sys.executable, str(Path(__file__).with_name("evaluate_chronos_historical.py")),
        "--model", str(args.chronos_model), "--panel", str(args.panel),
        "--output", str(chronos_output),
    ], check=True)
    chronos_wall_seconds = time.perf_counter() - started
    for name in sorted(expected_files):
        reference = pd.read_csv(args.chronos_reference / name)
        actual = pd.read_csv(chronos_output / name)
        keys = ["unique_id", "ds", "target_name"]
        if list(actual.columns) != list(reference.columns):
            raise ValueError("Chronos prediction columns differ")
        if not actual[keys].equals(reference[keys]):
            raise ValueError("Chronos prediction rows differ")
        numeric = [col for col in reference.columns if col not in keys]
        values = (actual[numeric] - reference[numeric]).abs()
        if values.isna().any().any() or not (values <= 1e-6).all().all():
            raise ValueError("Chronos prediction values differ")
        comparisons.append({"model": "Chronos-2", "file": name, "rows": len(actual),
                            "maximum_absolute_prediction_error": float(values.max().max()),
                            "reference_sha256": digest(args.chronos_reference / name),
                            "reproduced_sha256": digest(chronos_output / name)})
    report = {
        "status": "locked_cpu_forecast_inference_reproduced",
        "python_version": platform.python_version(), "system": platform.system(),
        "machine": platform.machine(), "libc": list(platform.libc_ver()),
        "packages": packages, "lock_sha256": digest(args.lock),
        "script_sha256": digest(Path(__file__)),
        "nhits_report_sha256": digest(args.nhits / "report.json"),
        "nhits_model_sha256": models,
        "panel_sha256": {name: digest(args.panel / name) for name in feeds},
        "chronos_model_sha256": {name: digest(args.chronos_model / name)
                                 for name in ("config.json", "model.safetensors")},
        "comparisons": comparisons,
        "chronos_process_wall_seconds": chronos_wall_seconds,
        "tolerance": 1e-6,
        "limitations": [
            "Saved-model CPU inference only; neural training determinism is not verified",
            "Package hashes must be enforced separately at installation",
            "Operating system, Python binary and native system libraries are not locked",
            "Previously inspected historical outcomes; no prospective evaluation or trading approval",
        ],
        "approved_for_training": False, "approved_for_execution": False,
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"PASS: {len(packages)} exact packages, {len(comparisons)} forecast comparisons")


if __name__ == "__main__":
    main()

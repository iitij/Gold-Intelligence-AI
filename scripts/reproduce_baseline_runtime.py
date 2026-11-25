"""Verify locked baseline packages and reproduce previously saved classifier predictions."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
from pathlib import Path

from predict_historical_model import predict


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locks", nargs="+", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--feed", required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    expected = {}
    for lock in args.locks:
        for name, version in re.findall(r"^([\w.-]+)==([^\s\\]+)", lock.read_text(), re.M):
            name = normalize(name)
            if name in expected and expected[name] != version:
                raise ValueError(f"Conflicting version pins: {name}")
            expected[name] = version
    if not expected:
        raise ValueError("No exact locked package pins")
    installed = {normalize(dist.metadata["Name"]): dist.version
                 for dist in importlib.metadata.distributions()}
    if expected != installed:
        raise ValueError("Installed distribution set must exactly match the supplied locks")
    reference = json.loads(args.reference.read_text())
    if digest(args.input) != reference["evaluation_source_sha256"]:
        raise ValueError("Evaluation source fingerprint differs from reference")
    comparisons = []
    if not reference["predictions"]:
        raise ValueError("Reference has no predictions")
    for original in reference["predictions"]:
        reproduced = predict(args.root, args.feed, original["horizon_bars"], original["model"],
                             args.input, as_of=reference["as_of_native"])
        differences = {key: abs(original[key] - reproduced[key]) for key in (
            "raw_up_probability", "calibrated_up_probability",
        )}
        if any(error > 1e-12 for error in differences.values()):
            raise ValueError("Reproduced prediction differs from the reference")
        for key in ("model_sha256", "decision_server_time", "as_of_server_time"):
            if original[key] != reproduced[key]:
                raise ValueError(f"Reproduced metadata mismatch: {key}")
        comparisons.append({"prediction": reproduced, "absolute_errors": differences})
    report = {
        "status": "locked_baseline_runtime_reproduced",
        "scope": "CPU baseline package set and saved-model inference on this Linux host",
        "python_version": platform.python_version(), "machine": platform.machine(),
        "system": platform.system(), "libc": list(platform.libc_ver()),
        "locks": {str(path): digest(path) for path in args.locks},
        "installed_packages": installed,
        "evaluation_source_sha256": digest(args.input),
        "reference_sha256": digest(args.reference),
        "model_report_sha256": digest(args.root / "report.json"),
        "script_sha256": digest(Path(__file__)),
        "prediction_comparisons": comparisons,
        "limitations": [
            "Does not lock the operating system, Python executable, compiler or native system libraries",
            "Does not cover neural forecasting, GPU, LLM or Windows MT5 environments",
            "Inference reproduction alone does not prove deterministic training or trading readiness",
            "Package wheel hashes are enforced by the separate installation command",
        ],
    }
    with args.output.open("x") as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"PASS: {len(installed)} exact packages, {len(comparisons)} reproduced predictions")


if __name__ == "__main__":
    main()

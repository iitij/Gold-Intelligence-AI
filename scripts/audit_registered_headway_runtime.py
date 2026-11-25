"""Verify frozen Headway inputs and model loading without opening holdout quotes."""

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from score_registered_classifiers import (
    FEED,
    HORIZONS,
    MODEL_ROOT,
    MODELS,
    PROTOCOL,
    check_runtime,
    digest,
    frozen_file,
    load_predictor,
    load_priors,
)

from goldintel.research.holdout import read_protocol, verify_frozen_files


def audit(frozen):
    import pandas as pd

    protocol_sha = PROTOCOL.with_suffix(".sha256").read_text().strip()
    protocol = read_protocol(PROTOCOL, protocol_sha)
    verify_frozen_files(protocol, frozen)
    if (protocol["server"], protocol["symbol"], protocol["secondary"]["models"],
            protocol["secondary"]["horizons_M15"]) != ("Headway-Demo", "XAUUSD", list(MODELS), list(HORIZONS)):
        raise ValueError("Unexpected registered scope")
    installed = check_runtime(frozen)
    training = json.loads(frozen_file(protocol, frozen, f"{MODEL_ROOT}/report.json").read_bytes())
    config = training["feeds"][FEED]
    priors = load_priors(protocol, frozen, config)
    predict = load_predictor(protocol, frozen, config, training)
    # A synthetic one-row vector checks the file loader, feature order, output
    # shape and calibration through the same path used after release.
    synthetic = pd.DataFrame([[0.0] * len(config["features"])], columns=config["features"])
    cases = []
    for horizon in HORIZONS:
        for model in MODELS:
            raw, calibrated = predict(horizon, model, synthetic)
            if any(series.shape != (1,) or not math.isfinite(series[0]) or not 0 <= series[0] <= 1
                   for series in (raw, calibrated)):
                raise ValueError(f"Unexpected synthetic output shape or probability: {model}, horizon {horizon}")
            cases.append({"model": model, "horizon_m15": horizon})
    from score_registered_classifiers import __file__ as scorer_file

    now = datetime.now(timezone.utc)
    return {"schema_version": 1, "observed_at_utc": now.isoformat(),
            "protocol_sha256": protocol_sha, "scorer_sha256": digest(Path(scorer_file)),
            "frozen_files_verified": len(protocol["frozen_files"]), "locked_packages_matched": len(installed),
            "historical_priors_recomputed": len(priors), "synthetic_load_and_calibration_cases": cases,
            "scheduled_release_utc": protocol["end_exclusive_utc"],
            "scheduled_release_passed": now >= datetime.fromisoformat(protocol["end_exclusive_utc"]),
            "holdout_inputs_opened": False, "holdout_scored": False,
            "complete_holdout_evidence": False, "approved_for_trading": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frozen", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = audit(args.frozen)
    with args.output.open("x") as output:
        output.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(f"Verified {result['frozen_files_verified']} frozen files and "
          f"{len(result['synthetic_load_and_calibration_cases'])} synthetic cases")


if __name__ == "__main__":
    main()

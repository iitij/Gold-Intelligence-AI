"""Reconstruct frozen classifier inputs as observed in a Headway research snapshot."""

import argparse
import csv
import io
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from build_headway_market_snapshot import EPOCH, build, digest, ordered_bracket, parse_utc
from capture_headway_market_inputs import MODEL_HISTORY_COUNT, OHLC
from score_registered_classifiers import (
    FEED,
    HORIZONS,
    MODEL_ROOT,
    MODELS,
    PROTOCOL,
    check_runtime,
    frozen_file,
    load_predictor,
)

from goldintel.data.mt5_csv import COLUMNS, TIME_FORMAT
from goldintel.data.snapshot import load_market_snapshot
from goldintel.research.holdout import assert_no_sealed_overlap, read_protocol, verify_frozen_files

M15 = timedelta(minutes=15)


def native_history(raw, ntp, offset, snapshot):
    """Retain completed rows observed before the quote and overlap-check the snapshot."""
    expected = snapshot.as_dict()
    history = raw["model_history"]
    clock_start = parse_utc(ntp["checked_before_utc"])
    recent = raw["frames"]["M15"]
    before, after = ordered_bracket(
        history, clock_start, parse_utc(recent["host_utc_before"]), timedelta(seconds=3),
    )
    rows = history["bars"]
    if len(rows) != MODEL_HISTORY_COUNT:
        raise ValueError("The bounded 300-row history did not arrive in full")
    stamps = [row["native_open_seconds"] for row in rows]
    if any(type(t) is not int or t <= 0 or t % 900 for t in stamps) or sorted(set(stamps)) != stamps:
        raise ValueError("Model history has invalid native M15 times")
    naive = EPOCH.replace(tzinfo=None)
    native_before = before.replace(tzinfo=None) + timedelta(seconds=offset)
    native_after = after.replace(tzinfo=None) + timedelta(seconds=offset)
    if naive + timedelta(seconds=stamps[-1]) > native_after:
        raise ValueError("Future native candle in model history")
    completed = {
        stamp: row for row, stamp in zip(rows[:-1], stamps[:-1], strict=True)
        if naive + timedelta(seconds=stamp) + M15 <= native_before
    }
    latest = [item for item in expected["bars"] if item["timeframe"] == "M15"]
    if len(latest) != 2 or not completed:
        raise ValueError("Snapshot does not contain the eligible M15 anchors")

    # Match independently requested M15 rows, including the exact inputs
    # that are lost when the four-bar snapshot is reduced to OHLC.
    overlap = 0
    for row in recent["bars"]:
        stamp = row["native_open_seconds"]
        if stamp in completed:
            old = completed[stamp]
            if (any(Decimal(row[k]) != Decimal(old[k]) for k in OHLC)
                    or any(row[k] != old[k] for k in ("tick_volume", "spread", "real_volume"))):
                raise ValueError("Repeated M15 history read differs")
            overlap += 1
    for bar in latest:
        native = parse_utc(bar["opened_at_utc"]) + timedelta(seconds=offset)
        stamp = (native - EPOCH) // timedelta(seconds=1)
        row = completed.get(stamp)
        if row is None or any(Decimal(row[k]) != Decimal(bar[k]) for k in OHLC):
            raise ValueError("Model context differs from the snapshot's completed M15 rows")
    latest_open = parse_utc(latest[-1]["opened_at_utc"]) + timedelta(seconds=offset)
    if max(completed) != (latest_open - EPOCH) // timedelta(seconds=1):
        raise ValueError("Model history's final closed bar differs from snapshot decision anchor")
    dated = [(naive + timedelta(seconds=stamp), row) for stamp, row in completed.items()]
    dates = sorted({t.date() for t, _ in dated})
    if len(dates) < 3:
        raise ValueError("Previous native date may be truncated by the capture boundary")
    previous = dates[-2]
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(COLUMNS)
    for t, row in dated:
        writer.writerow(["XAUUSD", "M15", t.strftime(TIME_FORMAT), *(row[k] for k in OHLC),
                         row["tick_volume"], row["spread"], row["real_volume"]])
    return output.getvalue().encode(), {
        "rows_used": len(dated), "matching_recent_bars": overlap,
        "previous_native_date": previous.isoformat(),
        "previous_native_date_rows": sum(t.date() == previous for t, _ in dated),
        "first_native_open": dated[0][0].isoformat(),
        "last_native_close": (dated[-1][0] + M15).isoformat(),
        "feature_bar_close_utc": latest[-1]["closed_at_utc"],
        "model_history_observed_at_utc": after.isoformat(),
    }


def predict_frozen(series, context, protocol, frozen):
    import numpy as np
    import pandas as pd

    report = json.loads(frozen_file(protocol, frozen, f"{MODEL_ROOT}/report.json").read_bytes())
    config = report["feeds"][FEED]
    source = frozen_file(protocol, frozen, "scripts/train_historical_strategies.py").resolve()
    sys.path.insert(0, str(source.parent))
    from train_historical_strategies import samples

    if Path(sys.modules[samples.__module__].__file__).resolve() != source:
        raise ValueError("Canonical feature builder did not load from the frozen snapshot")
    utils = frozen_file(protocol, frozen, "scripts/research_m15_direction.py").resolve()
    if Path(sys.modules["research_m15_direction"].__file__).resolve() != utils:
        raise ValueError("Canonical timeframe dependency did not load from the frozen snapshot")
    validator = Path(sys.modules["goldintel.data.mt5_csv"].__file__).read_bytes()
    if digest(validator) != protocol["frozen_files"]["src/goldintel/data/mt5_csv.py"]:
        raise ValueError("Bar validation dependency differs from the frozen snapshot")
    with tempfile.TemporaryDirectory(prefix="headway-model-input-") as temp:
        path = Path(temp) / "bars.csv"
        path.write_bytes(series)
        features, _, _, audit = samples(path, as_of=context["last_native_close"])
    if audit.source_sha256 != digest(series):
        raise ValueError("Feature input fingerprint differs")
    if features.empty or features.decision_server_time.iloc[-1] != pd.Timestamp(context["last_native_close"]):
        raise ValueError("No feature row at the exact anchor")
    columns = config["features"]
    row = features.iloc[[-1]][columns]
    if not np.isfinite(row.to_numpy()).all():
        raise ValueError("Most recent model feature row is incomplete")
    predict = load_predictor(protocol, frozen, config, report)
    results = []
    for h in HORIZONS:
        for name, extension in MODELS.items():
            raw, adjusted = predict(h, name, row)
            if not (0 <= raw[0] <= 1 and 0 <= adjusted[0] <= 1):
                raise ValueError("Frozen classifier probability outside valid range")
            relative = f"{Path(FEED).stem}/{h}-{extension}"
            results.append({
                "model": name, "horizon_bars": h, "raw_up_probability": float(raw[0]),
                "calibrated_up_probability": float(adjusted[0]),
                "model_sha256": report["model_sha256"][relative],
            })
    return columns, {k: float(row[k].iloc[0]) for k in columns}, results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--clock-evidence", required=True, type=Path)
    parser.add_argument("--host-clock-evidence", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--frozen-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    # Archive-only reconstruction. Report status at reconstruction time so old
    # packets cannot masquerade as a current, usable market decision.
    snapshot = load_market_snapshot(args.snapshot, args.snapshot_id)
    decision_at = parse_utc(snapshot.as_dict()["decision_at_utc"])
    now = datetime.now(timezone.utc)
    if now < decision_at:
        raise ValueError("Snapshot was not yet available")
    assert_no_sealed_overlap(
        PROTOCOL.parent / "holdout_registry.json", now=now,
        start=decision_at, end=decision_at + timedelta(microseconds=1),
    )
    source_bytes = {"capture": args.capture.read_bytes(), "clock": args.clock_evidence.read_bytes(),
                    "ntp": args.host_clock_evidence.read_bytes()}
    raw, anchor, ntp = (json.loads(source_bytes[k]) for k in ("capture", "clock", "ntp"))
    rebuilt, receipt = build(raw, anchor, ntp, source_bytes)
    if rebuilt != snapshot or not rebuilt.as_dict()["features"]:
        raise ValueError("Capture does not reconstruct its snapshot and completed bar features")
    series, context = native_history(raw, ntp, receipt["native_minus_utc_seconds"], snapshot)
    protocol_sha = PROTOCOL.with_suffix(".sha256").read_text().strip()
    protocol = read_protocol(PROTOCOL, protocol_sha)
    verify_frozen_files(protocol, args.frozen_root)
    installed = check_runtime(args.frozen_root)
    columns, values, results = predict_frozen(series, context, protocol, args.frozen_root)
    report = {
        "schema_version": 1, "scope": "retrospective market snapshot classifier reconstruction",
        "snapshot_id": snapshot.snapshot_id, "snapshot_at_observation": snapshot.status_at(decision_at),
        "snapshot_at_reconstruction": snapshot.status_at(now),
        "reconstructed_at_utc": now.isoformat(), "status": "research_attachment",
        "snapshot_source_chain_sha256": receipt["source_chain_sha256"],
        "model_input_sha256": digest(series), "protocol_sha256": protocol_sha,
        "model_context": context, "feature_columns": columns, "feature_values": values,
        "forecast_probabilities": results, "installed_packages": installed,
        "script_sha256": digest(Path(__file__).read_bytes()),
        "limitations": ["Model date features use native calendar, as in frozen training",
                        "Prior native session completeness beyond the observed archive is unverified",
                        "Research inference at the captured as-of; no forecast performance assessed",
                        "Unverified calendar blocks snapshot usability; execution remains disabled"],
        "execution_ready": False,
    }
    args.output.mkdir()
    (args.output / "model-input.csv").write_bytes(series)
    (args.output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print("Reconstructed six research probabilities for the verified snapshot")


if __name__ == "__main__":
    main()

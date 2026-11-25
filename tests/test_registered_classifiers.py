"""Verify classifier release and data-evidence controls."""

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from scripts.score_registered_classifiers import PROTOCOL, read_clock_evidence, score_frame

START = datetime(2026, 1, 3, tzinfo=timezone.utc)
END = START + timedelta(hours=2)
BROKER = {"server": "Headway-Demo", "symbol": "XAUUSD"}


def test_cli_rejects_sealed_inputs_before_opening_paths(tmp_path):
    protocol = json.loads(PROTOCOL.read_bytes())
    if datetime.now(timezone.utc) >= datetime.fromisoformat(protocol["end_exclusive_utc"]):
        pytest.skip("The registered window is now released")
    output = tmp_path / "result"
    result = subprocess.run([
        sys.executable, str(PROTOCOL.parents[1] / "scripts/score_registered_classifiers.py"),
        str(tmp_path / "missing-bars.csv"), "--clock-evidence", str(tmp_path / "missing-clock.json"),
        "--frozen-root", str(tmp_path / "missing-frozen"), "--output", str(output),
    ], capture_output=True, text=True, check=False)
    assert result.returncode and "remains sealed" in result.stderr
    assert "FileNotFoundError" not in result.stderr
    assert not output.exists()


def test_clock_evidence_requires_verified_hashes_and_full_coverage(tmp_path):
    path = tmp_path / "clock.json"
    evidence = tmp_path / "capture"
    evidence.write_text("evidence demonstration")
    entry = {"start_utc": START.isoformat(), "end_exclusive_utc": END.isoformat(),
             "native_minus_utc_seconds": 7200,
             "evidence_sha256": {evidence.name: hashlib.sha256(evidence.read_bytes()).hexdigest()}}
    data = {"schema_version": 1, **BROKER, "bars_sha256": "a" * 64, "intervals": [entry]}
    path.write_text(json.dumps(data))
    assert read_clock_evidence(path, "a" * 64, START, END, BROKER) == [(START, END, 7200)]
    with pytest.raises(ValueError, match="does not identify"):
        read_clock_evidence(path, "b" * 64, START, END, BROKER)
    entry["end_exclusive_utc"] = (END - timedelta(minutes=15)).isoformat()
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="cover"):
        read_clock_evidence(path, "a" * 64, START, END, BROKER)
    evidence.write_text("changed")
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        read_clock_evidence(path, "a" * 64, START, END, BROKER)


def test_common_cohort_excludes_gap_and_end_boundary():
    pd = pytest.importorskip("pandas")
    np = pytest.importorskip("numpy")
    # Opens occur from one quarter before start, with one missing inside the window.
    opened = pd.Series(pd.date_range("2026-01-03T01:45", periods=10, freq="15min").delete(3))
    features = pd.DataFrame({"decision_server_time": opened + timedelta(minutes=15), "a": 1.0})
    bars = pd.DataFrame({"close": range(len(opened))})

    def predict(h, name, x):
        return np.full(len(x), .6), np.full(len(x), .75)

    coverage, results, ledgers = score_frame(features, bars, opened,
        [(START - timedelta(minutes=15), END + timedelta(hours=1), 7200)], START, END,
        ["a"], {1: .5, 4: .5, 16: .5}, predict)
    assert coverage["possible_quarter_hours"] == 8
    assert coverage["missing_decision_times_utc"] == ["2026-01-03T00:45:00+00:00"]
    assert results["1"]["rows"] == 5
    assert results["1"]["feature_eligible_rows_with_unavailable_or_out_of_window_outcomes"] == 2
    for value in results["1"]["models"].values():
        assert value == {"brier": .0625, "brier_minus_prior": -.1875}
    assert list(ledgers["1"].outcome_utc)[-1] == "2026-01-03T01:45:00+00:00"
    assert results["16"]["prior_brier"] is None

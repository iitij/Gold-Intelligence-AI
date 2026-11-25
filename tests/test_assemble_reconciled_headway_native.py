"""Native staging must preserve equal-time quotes and refuse changed inputs."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from scripts.audit_headway_tick_batches import EPOCH, native_bound


def test_native_staging_preserves_ticks_and_rejects_changed_file(tmp_path):
    start, middle, end = "2026-11-25T16:00:00Z", "2026-11-25T16:02:00Z", "2026-11-25T16:04:00Z"
    stamp = int((native_bound(start) - EPOCH).total_seconds() * 1000)
    body = f"{stamp},1.00,1.01,6\n{stamp},1.00,1.02,6\n"
    raw = ("time_msc,bid,ask,flags\n" + body).encode()
    batches = tmp_path / "batches"
    batches.mkdir()
    tick = batches / "20261125T160000_20261125T160200.csv"
    tick.write_bytes(raw)
    source = tmp_path / "reconciled.json"
    source.write_text(json.dumps({
        "schema_version": 1, "server": "Headway-Demo", "symbol": "XAUUSD",
        "all_requests_reconciled": True, "attempts": [{"attempt": str(tmp_path)}],
        "window_status_counts": {"saved_verified": 1, "reported_empty": 1},
        "windows": [{"native_start": start, "native_end_exclusive": middle, "status": "saved_verified",
                     "observations": [{"status": "saved_verified", "attempt_index": 0, "file": tick.name,
                                       "rows": 2, "sha256": hashlib.sha256(raw).hexdigest()}]},
                    {"native_start": middle, "native_end_exclusive": end, "status": "reported_empty",
                     "observations": [{"status": "reported_empty"}]}],
    }))
    script = Path(__file__).resolve().parents[1] / "scripts/assemble_reconciled_headway_native.py"
    command = [sys.executable, str(script), str(source), hashlib.sha256(source.read_bytes()).hexdigest()]
    output = tmp_path / "staged"
    subprocess.run([*command, str(output)], check=True)
    assert (output / "quotes-native.csv").read_text() == "native_time_msc,bid,ask,flags\n" + body
    report = json.loads((output / "manifest.json").read_text())
    assert report["quote_rows"] == 2 and report["window_status_counts"]["reported_empty"] == 1
    assert not report["utc_mapping_verified"] and not report["evaluation_ready"]
    tick.write_bytes(raw.replace(b"1.01", b"1.02"))
    rejected = tmp_path / "rejected"
    result = subprocess.run([*command, str(rejected)], check=False, capture_output=True, text=True)
    assert result.returncode != 0 and "Reconciled tick fingerprint changed" in result.stderr
    assert not rejected.exists()

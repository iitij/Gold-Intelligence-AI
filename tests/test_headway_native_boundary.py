"""A published close need not line up with the two-minute quote export grid."""

import hashlib
import json

from scripts.audit_headway_tick_batches import EPOCH, native_bound
from scripts.probe_headway_native_boundary import MILLISECOND, probe


def test_odd_minute_boundary_separates_ticks_and_keeps_missing_windows_visible(tmp_path):
    boundary = native_bound("2026-11-26T21:15:00Z")
    center = (boundary - EPOCH) // MILLISECOND
    start, end = "2026-11-26T21:14:00Z", "2026-11-26T21:16:00Z"
    batches = tmp_path / "batches"
    batches.mkdir()
    file = batches / "20261126T211400_20261126T211600.csv"
    raw = f"time_msc,bid,ask,flags\n{center - 1},1,2,6\n{center},1,2,6\n".encode()
    file.write_bytes(raw)
    reconciliation = tmp_path / "reconciliation.json"
    reconciliation.write_text(json.dumps({
        "schema_version": 1, "server": "Headway-Demo", "symbol": "XAUUSD",
        "attempts": [{"attempt": str(tmp_path)}],
        "windows": [{"native_start": start, "native_end_exclusive": end, "status": "saved_verified",
                     "observations": [{"status": "saved_verified", "attempt_index": 0, "file": file.name,
                                       "rows": 2, "sha256": hashlib.sha256(raw).hexdigest()}]}],
    }))
    report = probe(reconciliation, boundary)
    assert report["observed_ticks_before"] == report["observed_ticks_at_or_after"] == 1
    assert report["closest_before_native"] == "2026-11-26T21:14:59.999000+00:00"
    assert report["closest_at_or_after_native"] == boundary.isoformat()
    assert report["request_status_counts"] == {"saved_verified": 1, "missing_from_report": 12}
    assert not report["all_probe_requests_accounted_for"]
    assert not report["trade_session_verified"]

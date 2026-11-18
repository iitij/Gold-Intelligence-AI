"""Validate batch accounting at request boundaries and under interrupted collection."""

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.audit_headway_tick_batches import audit_batches

START = datetime(2026, 11, 18, 13, tzinfo=timezone.utc)
STEP = timedelta(minutes=2)
ROOT = Path(__file__).resolve().parents[1]


def file_for(directory, start, end, stamps):
    path = directory / f"{start:%Y%m%dT%H%M%S}_{end:%Y%m%dT%H%M%S}.csv"
    body = [f"{stamp},{bid},{ask},6" for stamp, bid, ask in stamps]
    path.write_text("time_msc,bid,ask,flags\n" + "\n".join(body) + "\n")
    return path


def log_for(directory, end, entries):
    log = directory / "export.log"
    lines = ["Connecting to MT5", f"Headway-Demo verified; requesting XAUUSD from {START} to {end}"]
    for lower, upper, result in entries:
        lines.append(f"Request {lower.isoformat()} through {upper.isoformat()} exclusive")
        if result is not None:
            lines.append(result)
    log.write_text("\n".join(lines) + "\n")
    return log


def ms(stamp):
    return int(stamp.timestamp()) * 1000


def test_complete_receipts_allow_empty_tail_and_preserve_same_millisecond_rows(tmp_path):
    first_end = START + STEP
    end = first_end + timedelta(minutes=1)
    t = ms(START)
    file_for(tmp_path, START, first_end, [(t, 3800, 3801), (t, 3800, 3802), (t, 3800, 3801)])
    log = log_for(tmp_path, end, [
        (START, first_end, "Saved 3 rows"), (first_end, end, "Empty quote window"),
    ])
    result = audit_batches(tmp_path, log, START, end)
    assert result["all_request_windows_accounted_for"] is True
    assert result["window_status_counts"] == {"saved_verified": 1, "reported_empty": 1}
    assert result["same_timestamp_rows"] == 2
    assert result["repeated_export_rows"] == 1
    assert result["total_stored_rows"] == 3
    assert result["utc_mapping_verified"] is False


def test_interrupted_export_distinguishes_missing_reported_file_and_unaccounted(tmp_path):
    second = START + STEP
    third = second + STEP
    end = third + STEP
    file_for(tmp_path, START, second, [(ms(START), 3800, 3801)])
    log = log_for(tmp_path, end, [(second, third, "Saved 1 rows"), (third, end, None)])
    output = tmp_path / "audit.json"
    proc = subprocess.run([
        sys.executable, str(ROOT / "scripts/audit_headway_tick_batches.py"),
        str(tmp_path), str(log), str(output), "--start", START.isoformat(), "--end", end.isoformat(),
    ], capture_output=True, text=True, check=False)
    assert proc.returncode == 2
    result = json.loads(output.read_text())
    assert not result["all_request_windows_accounted_for"]
    assert not result["log_ends_with_completed_request"]
    assert result["window_status_counts"] == {
        "file_without_receipt": 1, "missing_reported_file": 1, "unaccounted": 1,
    }


@pytest.mark.parametrize("tick,result,error", [
    ("end", "Saved 1 rows", "invalid time"),
    ("crossed", "Saved 1 rows", "Bid/Ask"),
    ("valid", "Saved 2 rows", "contradicts"),
    ("valid", "Empty quote window", "contradicts"),
])
def test_reject_outside_half_open_bounds_and_log_contradictions(tmp_path, tick, result, error):
    end = START + STEP
    stamp = ms(end if tick == "end" else START)
    file_for(tmp_path, START, end, [(stamp, 3800, 3799 if tick == "crossed" else 3801)])
    log = log_for(tmp_path, end, [(START, end, result)])
    with pytest.raises(ValueError, match=error):
        audit_batches(tmp_path, log, START, end)


def test_reject_file_with_overlapping_window_even_if_quotes_look_valid(tmp_path):
    end = START + 2 * STEP
    file_for(tmp_path, START, end, [(ms(START), 3800, 3801)])
    log = log_for(tmp_path, end, [])
    with pytest.raises(ValueError, match="overlapping"):
        audit_batches(tmp_path, log, START, end)

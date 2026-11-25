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


@pytest.mark.parametrize("first_result,second_result,contradictory", [
    ("Saved 1 rows", "Saved 1 rows", False),
    ("Saved 1 rows", "Empty quote window", True),
    ("Saved 2 rows", "Saved 1 rows", True),
])
def test_reconcile_retry_requires_consistent_receipts(
    tmp_path, first_result, second_result, contradictory,
):
    middle = START + STEP
    end = middle + STEP
    initial, repeat = tmp_path / "initial", tmp_path / "repeat"
    for directory in initial, repeat:
        (directory / "batches").mkdir(parents=True)
    if first_result == "Saved 1 rows":
        file_for(initial / "batches", START, middle, [(ms(START), 3800, 3801)])
    log_for(initial, end, [(START, middle, first_result), (middle, end, None)])
    if second_result == "Saved 1 rows":
        file_for(repeat / "batches", START, middle, [(ms(START), 3800, 3801)])
    file_for(repeat / "batches", middle, end, [(ms(middle), 3801, 3802)])
    log_for(repeat, end, [(START, middle, second_result), (middle, end, "Saved 1 rows")])
    output = tmp_path / "combined.json"
    proc = subprocess.run([
        sys.executable, str(ROOT / "scripts/reconcile_headway_attempts.py"), str(output),
        "--start", START.isoformat(), "--end", end.isoformat(),
        "--attempt", str(initial), START.isoformat(), end.isoformat(),
        "--attempt", str(repeat), START.isoformat(), end.isoformat(),
    ], capture_output=True, text=True, check=False)
    assert proc.returncode == (2 if contradictory else 0), proc.stderr
    report = json.loads(output.read_text())
    assert report["all_requests_reconciled"] is (not contradictory)
    assert report["holdout_data_complete"] is False
    assert report["windows"][0]["status"] == (
        "conflicting_observations" if contradictory else "saved_verified"
    )
    assert [row["status"] for row in report["windows"][1]["observations"]] == [
        "unaccounted", "saved_verified",
    ]


def test_extension_refuses_rewritten_previous_quote_file(tmp_path):
    from hashlib import sha256

    mid, end = START + STEP, START + 2 * STEP
    old, new = tmp_path / "old", tmp_path / "new"
    for root in (old, new):
        (root / "batches").mkdir(parents=True)
    old_tick = file_for(old / "batches", START, mid, [(ms(START), 3800, 3801)])
    file_for(new / "batches", mid, end, [(ms(mid), 3801, 3802)])
    log_for(old, mid, [(START, mid, "Saved 1 rows")])
    log_for(new, end, [(mid, end, "Saved 1 rows")]).write_text(
        f"Connecting to MT5\nHeadway-Demo verified; requesting XAUUSD from {mid} to {end}\n"
        f"Request {mid.isoformat()} through {end.isoformat()} exclusive\nSaved 1 rows\n"
    )
    anchor = tmp_path / "anchor.json"
    observed = START.replace(hour=11, minute=5)
    begun = observed + timedelta(minutes=1)
    anchor.write_text(json.dumps({
        "status": "matching_current_headway_demo_quote_clock_and_export", "server": "Headway-Demo",
        "symbol": "XAUUSD", "ntp_before_after": True, "changed_quotes_matched": 10,
        "native_minus_utc_seconds": 7200, "last_host_observation_utc": observed.isoformat(),
    }))
    (new / "closed-request.json").write_text(json.dumps({
        "session_receipt_sha256": sha256(anchor.read_bytes()).hexdigest(),
        "requested_native_start": mid.isoformat(), "requested_native_end_exclusive": end.isoformat(),
        "request_not_before_utc": begun.isoformat(), "request_finished_utc": begun.isoformat(),
        "end_utc_under_session_offset": (end - timedelta(hours=2)).isoformat(),
        "host_clock_synchronized_after": True, "export_exit_code": 0, "closed_request_receipt_accepted": True,
        "audit": audit_batches(new / "batches", new / "export.log", mid, end),
    }))
    previous = tmp_path / "previous.json"
    cmd = [sys.executable, str(ROOT / "scripts/reconcile_headway_attempts.py")]
    subprocess.run([*cmd, str(previous), "--start", START.isoformat(), "--end", mid.isoformat(),
                    "--attempt", str(old), START.isoformat(), mid.isoformat()], check=True)
    previous_sha = sha256(previous.read_bytes()).hexdigest()
    extension = ["--start", START.isoformat(), "--end", end.isoformat(),
                 "--previous", str(previous), previous_sha, "--guarded-attempt", str(new), str(anchor)]
    output = tmp_path / "extended.json"
    subprocess.run([*cmd, str(output), *extension], check=True)
    report = json.loads(output.read_text())
    assert report["previous_report_sha256"] == previous_sha
    assert report["window_status_counts"] == {"saved_verified": 2}
    old_tick.write_text(old_tick.read_text().replace("3800,3801", "3799,3801"))
    rejected = tmp_path / "rejected.json"
    result = subprocess.run([*cmd, str(rejected), *extension], capture_output=True, text=True, check=False)
    assert result.returncode != 0 and "Previous windows changed" in result.stderr
    assert not rejected.exists()

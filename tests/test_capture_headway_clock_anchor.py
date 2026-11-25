"""A cached or delayed quote must not widen the clock export request."""

import json
from datetime import datetime, timedelta
from importlib import import_module
from pathlib import Path

import pytest


def test_capture_bounds_keep_the_observed_native_windows(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    sample_bounds = import_module("capture_headway_clock_anchor").sample_bounds
    first = datetime.fromisoformat("2026-11-25T17:23:59+00:00")
    rows = []
    for kind, stamp, lag in (
        ("initial_cached_quote", first - timedelta(days=1), 86_400),
        ("changed_quote", first, 0),
        ("changed_quote", first + timedelta(seconds=1), 0),
        ("changed_quote", first + timedelta(seconds=2), 0),
        ("changed_quote", first + timedelta(minutes=15), 10),
    ):
        host = stamp - timedelta(seconds=7200 - lag)
        rows.append({"kind": kind, "native_tick_ms": int(stamp.timestamp() * 1000),
                     "host_utc_before": host.isoformat(), "host_utc_after": host.isoformat()})
    clock = tmp_path / "clock.jsonl"
    clock.write_text("".join(json.dumps(row) + "\n" for row in rows))
    start, end = sample_bounds(clock, 7200)
    assert (start.isoformat(), end.isoformat()) == (
        "2026-11-25T17:22:00+00:00", "2026-11-25T17:26:00+00:00",
    )
    with pytest.raises(ValueError, match="Too few current observations"):
        sample_bounds(clock, 10800)

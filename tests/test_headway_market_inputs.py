"""Check live capture clock ordering and exclude bars still forming at read time."""

import importlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


@pytest.fixture
def market_inputs(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    builder = importlib.import_module("build_headway_market_snapshot")
    now = datetime(2026, 11, 18, 20, 59, 25, tzinfo=timezone.utc)
    starts = {"M15": 20 * 60 + 45, "H1": 20 * 60, "H4": 18 * 60}
    counts = {"M15": 40, "H1": 4, "H4": 3}
    raw = {"schema_version": 1, "kind": "observed_headway_market_inputs",
           "server": "Headway-Demo", "symbol": "XAUUSD", "frames": {}}
    for i, (tf, mins) in enumerate(starts.items()):
        last_open = now.replace(hour=0, minute=0, second=0) + timedelta(minutes=mins)
        before = now - timedelta(milliseconds=50 - i * 10)
        after = before + timedelta(milliseconds=10)
        bars = []
        for lag in reversed(range(counts[tf])):
            native = last_open + timedelta(hours=2) - timedelta(seconds=lag * builder.FRAME_SECONDS[tf])
            bars.append({"native_open_seconds": int(native.timestamp()),
                         "open": "3700", "high": "3702", "low": "3698", "close": "3701"})
        raw["frames"][tf] = {"host_utc_before": before.isoformat(), "host_utc_after": after.isoformat(),
                             "bars": bars}
    raw["quote"] = {"host_utc_before": now.isoformat(), "host_utc_after": now.isoformat(),
                    "native_tick_msc": int((now + timedelta(hours=2)).timestamp() * 1000),
                    "bid": "3700.5", "ask": "3700.9"}
    anchor = {"status": "matching_current_headway_demo_quote_clock_and_export", "server": "Headway-Demo",
              "symbol": "XAUUSD", "ntp_before_after": True, "changed_quotes_matched": 4,
              "native_minus_utc_seconds": 7200,
              "first_host_observation_utc": (now - timedelta(minutes=14)).isoformat(),
              "last_host_observation_utc": (now - timedelta(minutes=13)).isoformat()}
    ntp = {"checked_before_utc": (now - timedelta(seconds=1)).isoformat(),
           "checked_after_utc": (now + timedelta(seconds=1)).isoformat(),
           "before": "NTPSynchronized=yes", "after": "NTPSynchronized=yes"}

    def build():
        records = {"capture": raw, "clock": anchor, "ntp": ntp}
        return builder.build(raw, anchor, ntp, {name: json.dumps(d).encode() for name, d in records.items()})
    return raw, anchor, ntp, now, build


def test_unfinished_quotes_do_not_enter_features_and_availability_is_observed(market_inputs):
    raw, _, _, now, build = market_inputs
    original, receipt = build()
    for frame in raw["frames"].values():
        frame["bars"][-1]["high"] = "9999"
    updated, _ = build()
    before, after = original.as_dict(), updated.as_dict()
    assert before["features"] == after["features"]
    assert before["bars"] == after["bars"]
    assert before["snapshot_id"] != after["snapshot_id"]  # Source bundle changed.
    assert len(before["bars"]) == 4
    assert receipt["aggregation_matching_m15_rows"] == {"H1": 4, "H4": 16}
    assert before["blockers"] == ["calendar_coverage_unverified"]
    assert not before["execution_ready"]
    assert all(datetime.fromisoformat(b["closed_at_utc"])
               <= datetime.fromisoformat(b["available_at_utc"]) <= now for b in before["bars"])
    assert "snapshot_expired" in original.status_at(now + timedelta(seconds=61))["blockers"]


def test_mismatched_higher_frame_stops_snapshot(market_inputs):
    raw, _, _, _, build = market_inputs
    raw["frames"]["H4"]["bars"][-2]["high"] = "4999"
    with pytest.raises(ValueError, match="H4 OHLC differs"):
        build()


def test_wrong_session_offset_or_late_read_rejected(market_inputs):
    raw, anchor, _, now, build = market_inputs
    anchor["native_minus_utc_seconds"] = 10800
    with pytest.raises(ValueError, match="session offset"):
        build()
    anchor["native_minus_utc_seconds"] = 7200
    raw["frames"]["H4"]["host_utc_after"] = (now + timedelta(milliseconds=1)).isoformat()
    with pytest.raises(ValueError, match="out-of-envelope"):
        build()


def add_model_history(raw):
    recent = raw["frames"]["M15"]
    before = datetime.fromisoformat(recent["host_utc_before"]) - timedelta(milliseconds=10)
    older = [{**recent["bars"][0],
              "native_open_seconds": recent["bars"][0]["native_open_seconds"] - 900 * lag}
             for lag in reversed(range(1, 261))]
    for row in [*older, *recent["bars"]]:
        row.update({"tick_volume": 500, "spread": 20, "real_volume": 0})
    raw["model_history"] = {"host_utc_before": before.isoformat(),
                            "host_utc_after": recent["host_utc_before"],
                            "bars": [*older, *(row.copy() for row in recent["bars"])]}


def test_model_history_ignores_forming_bar_but_checks_used_volume(market_inputs):
    adapter = importlib.import_module("attach_headway_snapshot_forecasts")
    raw, anchor, ntp, _, build = market_inputs
    add_model_history(raw)
    snapshot, _ = build()
    context, details = adapter.native_history(raw, ntp, anchor["native_minus_utc_seconds"], snapshot)
    assert details["rows_used"] == 299
    assert details["matching_recent_bars"] == 39
    raw["model_history"]["bars"][-1]["close"] = "9999"
    raw["model_history"]["bars"][-1]["tick_volume"] = 300000
    repeated, _ = adapter.native_history(raw, ntp, anchor["native_minus_utc_seconds"], snapshot)
    assert repeated == context
    raw["model_history"]["bars"][-2]["tick_volume"] += 1
    with pytest.raises(ValueError, match="history read differs"):
        adapter.native_history(raw, ntp, anchor["native_minus_utc_seconds"], snapshot)


def test_context_observed_after_market_capture_cannot_be_attached(market_inputs):
    adapter = importlib.import_module("attach_headway_snapshot_forecasts")
    raw, anchor, ntp, _, build = market_inputs
    add_model_history(raw)
    snapshot, _ = build()
    raw["model_history"]["host_utc_after"] = raw["quote"]["host_utc_after"]
    with pytest.raises(ValueError, match="out-of-envelope"):
        adapter.native_history(raw, ntp, anchor["native_minus_utc_seconds"], snapshot)

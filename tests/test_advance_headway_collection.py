"""Checkpoint bounds must never request the live two-minute bucket."""

from datetime import datetime, timedelta
from importlib import import_module
from pathlib import Path


def test_checkpoint_uses_exact_closure_margin_and_caps_catchup(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    closed_end = import_module("advance_headway_collection").closed_end
    last = datetime.fromisoformat("2026-11-25T16:56:00+00:00")
    before = datetime.fromisoformat("2026-11-25T14:58:01.999999+00:00")
    after = datetime.fromisoformat("2026-11-25T14:58:02+00:00")
    assert closed_end(last, 7200, before) == last
    assert closed_end(last, 7200, after) == last + timedelta(minutes=2)
    assert closed_end(last, 7200, after + timedelta(days=2)) == last + timedelta(days=1)

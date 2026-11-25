"""Test edge minutes where a declared session is not a whole export window."""

import hashlib
from importlib import import_module
from pathlib import Path

import pytest


def test_empty_partial_closure_is_not_a_documented_closed_window(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    classify = import_module("audit_headway_quote_sessions").classify
    source = tmp_path / "calendar.txt"
    source.write_text("Synthetic quote schedule")
    evidence = {"path": source.name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}

    def bounds(start, end):
        return {"native_start": f"2026-11-26T21:{start:02d}:00Z",
                "native_end_exclusive": f"2026-11-26T21:{end:02d}:00Z"}

    scope = {"schema_version": 1, "server": "Headway-Demo", "symbol": "XAUUSD"}
    reconciliation = {**scope, "windows": [
        {**bounds(i, i + 2), "status": status}
        for i, status in ((14, "reported_empty"), (16, "reported_empty"),
                          (18, "reported_empty"), (20, "saved_verified"))
    ]}
    manifest = {**scope, "kind": "quote_session_evidence", "intervals": [
        {**bounds(15, 18), "state": "quote_closed", "evidence": evidence},
        {**bounds(18, 20), "state": "quote_open", "evidence": evidence},
        {**bounds(20, 22), "state": "quote_closed", "evidence": evidence},
    ]}
    result = classify(reconciliation, manifest, tmp_path)
    assert result["classification_counts"] == {
        "empty_without_full_closed_evidence": 1, "empty_with_full_closed_evidence": 1,
        "empty_overlaps_documented_open": 1, "saved_conflicts_with_full_closed_evidence": 1,
    }
    assert result["windows_review"][0]["unclassified_seconds"] == 60
    assert result["has_unresolved_market_windows"]
    with pytest.raises(ValueError, match="quote-session evidence"):
        classify(reconciliation, {**manifest, "kind": "trade_session_evidence"}, tmp_path)

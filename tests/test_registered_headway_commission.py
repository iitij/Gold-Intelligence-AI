"""A point sample cannot supply the constant fee required by the frozen replay."""

import hashlib
from datetime import datetime

import pytest

from scripts.audit_registered_headway_commission import audit

PROTOCOL = {"server": "Headway-Demo", "symbol": "XAUUSD",
            "start_utc": "2026-11-23T00:00:00Z", "end_exclusive_utc": "2026-11-25T00:00:00Z"}
NOW = datetime.fromisoformat("2026-11-25T00:00:01+00:00")


def test_point_cost_evidence_and_changing_costs_never_become_constant(tmp_path):
    source = tmp_path / "evidence.txt"
    source.write_text("Synthetic test evidence")
    evidence = {"path": source.name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    manifest = {"schema_version": 1, "server": "Headway-Demo", "symbol": "XAUUSD", "currency": "USD",
                "point_observations": [{"observed_at_utc": "2026-11-23T12:00:00Z", "evidence": evidence}],
                "intervals": []}
    report = audit(PROTOCOL, manifest, tmp_path, NOW)
    assert report["uncovered_intervals"] == [["2026-11-23T00:00:00+00:00", "2026-11-25T00:00:00+00:00"]]
    assert report["constant_commission_candidate"] is None
    shared = {"account_tier": "Standard", "account_terms_evidence": evidence,
              "contract_size_evidence": evidence, "contract_ounces_per_lot": "100"}
    manifest["intervals"] = [
        {**shared, "start_utc": f"2026-11-{day}T00:00:00Z", "end_exclusive_utc": f"2026-11-{day + 1}T00:00:00Z",
         "commission_usd_per_side_per_lot": str(day - 23)}
        for day in (23, 24)
    ]
    report = audit(PROTOCOL, manifest, tmp_path, NOW)
    assert report["complete_interval_coverage"]
    assert report["distinct_documented_rates_usd_per_side_per_ounce"] == ["0", "0.01"]
    assert report["constant_commission_candidate"] is None
    manifest["intervals"][0]["commission_usd_per_side_per_lot"] = "1"
    assert audit(PROTOCOL, manifest, tmp_path, NOW)["constant_commission_candidate"] == "0.01"
    manifest["intervals"][0]["end_exclusive_utc"] = "2026-11-24T00:01:00Z"
    with pytest.raises(ValueError, match="intervals overlap"):
        audit(PROTOCOL, manifest, tmp_path, NOW)

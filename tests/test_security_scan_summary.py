"""Scanner JSON parsing must fail closed and report vulnerable packages."""
import json

import pytest

from scripts.summarize_security_scan import (
    SecurityAuditError,
    generate,
    summarize_findings,
    summarize_sbom,
)


def test_cyclonedx_empty_or_bad_schema_is_rejected():
    with pytest.raises(SecurityAuditError):
        summarize_sbom({"bomFormat": "CycloneDX", "components": []})
    with pytest.raises(SecurityAuditError):
        summarize_sbom({"bomFormat": "SPDX", "components": [{"name": "pytest"}]})


def test_grype_report_severity_is_not_suppressed():
    info = summarize_findings({
        "matches": [
            {"vulnerability": {"id": "CVE-TEST", "severity": "High",
                               "fix": {"state": "fixed"}},
             "artifact": {"name": "fake-lib", "version": "1.0"}},
            {"vulnerability": {"id": "CVE-TEST-2", "severity": "Critical"},
             "artifact": {"name": "other", "version": "0"}},
        ]
    })
    assert info["total"] == 2
    assert info["by_severity"]["High"] == 1
    assert info["by_severity"]["Critical"] == 1
    assert "CVE-TEST" in {v["id"] for v in info["findings"]}


def test_security_scan_report_never_auto_accepts_g0(tmp_path):
    for label in ("ci_environment", "repository_sources"):
        (tmp_path / f"{label}.cdx.json").write_text(json.dumps({
            "bomFormat": "CycloneDX",
            "components": [{"name": "pytest"}, {"name": "ruff"}],
        }))
        (tmp_path / f"{label}.grype.json").write_text('{"matches":[]}')
    result = generate(tmp_path, "a" * 40)
    assert result["g0_approved"] is False
    assert result["manual_security_review_required"] is True
    assert result["scans"]["ci_environment"]["findings"]["total"] == 0


def test_scanner_missing_fields_fails_closed():
    with pytest.raises(SecurityAuditError):
        summarize_findings({})

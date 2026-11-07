"""Verify a dated Syft/Grype scan and explicit source-of-risk triage.

The scan is a frozen advisory snapshot. This tool does NOT update packages,
execute vendored source, or authorize training, demo or live trading.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = Path("planning/security/scans/one_time")
SEVERITIES = ("Critical", "High", "Medium", "Low", "Negligible", "Unknown")


class TriageError(ValueError):
    """Incomplete, ambiguous or tampered scan result."""


def load(path: Path) -> dict:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TriageError("Scan evidence cannot be loaded: " + str(path)) from exc
    if not isinstance(obj, dict):
        raise TriageError("Expected JSON object")
    return obj


def classify(scan: str, locations: list[str]) -> str:
    if not locations or any(not isinstance(p, str) or not p for p in locations):
        raise TriageError("Missing package evidence path")
    if scan == "repository_sources":
        if all(p.endswith("/vendor/snapshots/andyluu98--midas-agent/uv.lock")
               for p in locations):
            return "uninstalled_archived_midas_uv_lock"
        raise TriageError("Unclassified source advisory (manual review required)")
    if scan != "ci_environment":
        raise TriageError("Unexpected scan")
    if all("/site-packages/setuptools/_vendor/" in p for p in locations):
        return "ci_bootstrap_setuptools_bundled"
    if all(re.search(r"/site-packages/pip-[^/]+\.dist-info/", p)
           for p in locations):
        return "ci_bootstrap_pip"
    if all(re.search(r"/site-packages/setuptools-[^/]+\.dist-info/", p)
           for p in locations):
        return "ci_bootstrap_setuptools"
    raise TriageError("Unclassified installed package (manual review required)")


def derive(root: Path = ROOT) -> dict:
    directory = root / SCAN
    summary = load(directory / "triage_summary.json")
    if summary.get("g0_approved") is not False:
        raise TriageError("Scan baseline claims unearned G0 approval")
    scopes = {}
    critical_midas = set()
    high_ci = set()
    for key in ("ci_environment", "repository_sources"):
        sbom_path = directory / (key + ".cdx.json")
        sbom_bytes = sbom_path.read_bytes()
        bom = json.loads(sbom_bytes)
        source = summary["scans"][key]
        if bom.get("bomFormat") != "CycloneDX":
            raise TriageError("Unexpected SBOM format")
        if len(bom.get("components", [])) != source["sbom_components"]:
            raise TriageError("SBOM component count mismatch")
        if hashlib.sha256(sbom_bytes).hexdigest() != source["sbom_sha256"]:
            raise TriageError("SBOM digest mismatch")
        matches = load(directory / (key + ".grype.json")).get("matches")
        if not isinstance(matches, list) or len(matches) != source["findings"]["total"]:
            raise TriageError("Advisory inventory incomplete")
        sev = Counter()
        groups = Counter()
        for item in matches:
            vuln = item.get("vulnerability") or {}
            artifact = item.get("artifact") or {}
            paths = [p.get("path") for p in artifact.get("locations", [])]
            origin = classify(key, paths)
            severity = vuln.get("severity")
            if severity not in SEVERITIES:
                raise TriageError("Unrecognized severity")
            if not vuln.get("id") or not artifact.get("name"):
                raise TriageError("Unidentified matched vulnerability")
            sev[severity] += 1
            groups[origin] += 1
            if key == "repository_sources" and severity == "Critical":
                critical_midas.add(vuln["id"])
            if key == "ci_environment" and severity == "High":
                high_ci.add(vuln["id"])
        counts = {s: sev[s] for s in SEVERITIES}
        if counts != source["findings"]["by_severity"]:
            raise TriageError("Severity histogram mismatch")
        scopes[key] = {
            "components": source["sbom_components"],
            "matched_advisories": len(matches),
            "severities": counts,
            "origins": dict(groups),
        }
    return {
        "schema_version": 1,
        "scan_date_utc": summary["generated_at_utc"],
        "scan_source_commit": summary["source_commit"],
        "github_actions_run":
            "https://github.com/iitij/Gold-Intelligence-AI/actions/runs/42422206182",
        "classification_policy": (
            "Evidence-located baseline findings; archive metadata is not installed code; "
            "no suppressions"
        ),
        "scopes": scopes,
        "critical_archived_midas_advisories": sorted(critical_midas),
        "high_ci_bootstrap_advisories": sorted(high_ci),
        "installed_dev_tooling_needs_remediation_review": True,
        "archived_midas_runtime_approved": False,
        "all_runtime_dependencies_inventoried": False,
        "all_findings_mitigated": False,
        "independent_audit_complete": False,
        "g0_approved": False,
        "training_permitted": False,
        "live_trading_permitted": False,
    }


def verify(root: Path = ROOT) -> dict:
    expected = derive(root)
    recorded = load(root / SCAN / "triage_classification.json")
    if recorded != expected:
        raise TriageError("Security triage has drifted from raw scanner evidence")
    if (root / ".github/workflows/one-time-sbom-audit.yml").exists():
        raise TriageError("Temporary privileged security scanning workflow still active")
    return recorded


if __name__ == "__main__":
    report = verify()
    for scope, result in report["scopes"].items():
        print("PASS:", scope, result["matched_advisories"],
              "advisory matches assigned to evidence locations")
    print("REVIEW REQUIRED: G0 blocked; no training/demo/live authorization")

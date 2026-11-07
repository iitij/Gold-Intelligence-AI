"""Summarize pinned one-time Syft/Grype results. No vulnerability suppression.

Does not perform scans itself, does not declare vendor code safe, and never
authorizes execution. The report is a dated evidence artifact for manual triage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SEVERITY = ("Critical", "High", "Medium", "Low", "Negligible", "Unknown")


class SecurityAuditError(ValueError):
    """Scanner evidence is missing or malformed."""


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SecurityAuditError(f"Missing or invalid scan JSON: {path}") from exc
    if not isinstance(data, dict):
        raise SecurityAuditError("Expected JSON object from scanner")
    return data


def summarize_sbom(data: dict) -> dict:
    if data.get("bomFormat") != "CycloneDX":
        raise SecurityAuditError("Expected CycloneDX source SBOM")
    components = data.get("components")
    if not isinstance(components, list) or not components:
        raise SecurityAuditError("Scanner produced empty component inventory")
    names = sorted({
        item["name"].lower() for item in components
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    })
    return {"components_count": len(components), "names": names}


def summarize_findings(data: dict) -> dict:
    matches = data.get("matches")
    if not isinstance(matches, list):
        raise SecurityAuditError("Grype report missing matches array")
    count = Counter()
    rows = []
    for match in matches:
        if not isinstance(match, dict):
            raise SecurityAuditError("Unrecognized vulnerability match")
        vuln = match.get("vulnerability") or {}
        artifact = match.get("artifact") or {}
        severity = str(vuln.get("severity", "Unknown")).title()
        if severity not in SEVERITY:
            severity = "Unknown"
        count[severity] += 1
        rows.append({
            "id": str(vuln.get("id", "unidentified")),
            "severity": severity,
            "package": str(artifact.get("name", "unknown")),
            "version": str(artifact.get("version", "unknown")),
            "fix_state": str((vuln.get("fix") or {}).get("state", "unknown")),
        })
    return {"total": len(rows),
            "by_severity": {k: count[k] for k in SEVERITY},
            "findings": sorted(rows, key=lambda x: (
                SEVERITY.index(x["severity"]), x["package"], x["id"]))}


def generate(directory: Path, source_commit: str) -> dict:
    if len(source_commit) != 40 or any(
        c not in "0123456789abcdef" for c in source_commit
    ):
        raise SecurityAuditError("Full source commit SHA required")
    scans = {}
    for name in ("ci_environment", "repository_sources"):
        sbom_file = directory / f"{name}.cdx.json"
        vulns_file = directory / f"{name}.grype.json"
        sbom = summarize_sbom(read_json(sbom_file))
        report = summarize_findings(read_json(vulns_file))
        digest = hashlib.sha256(sbom_file.read_bytes()).hexdigest()
        scans[name] = {
            "sbom": sbom_file.name, "sbom_sha256": digest,
            "sbom_components": sbom["components_count"],
            "vulnerability_report": vulns_file.name,
            "findings": report,
        }
        if name == "ci_environment" and not {"pytest", "ruff"}.issubset(
            set(sbom["names"])
        ):
            raise SecurityAuditError(
                "CI installed packages not catalogued: need pytest and ruff"
            )
    return {
        "schema_version": 1,
        "source_commit": source_commit,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scanners": {
            "syft": "1.57.0; release tarball SHA256-pinned",
            "grype": "0.121.2; release tarball SHA256-pinned",
            "vulnerability_database": "online advisory snapshot at scan time; not pinned",
        },
        "scope": "GitHub runner Python 3.11 CI venv AND repository files incl archived vendor",
        "manual_security_review_required": True,
        "sbom_is_complete_for_all_runtime_dependencies": False,
        "code_security_audit_complete": False,
        "github_ruleset_enforced": False,
        "g0_approved": False,
        "scans": scans,
        "limitations": [
            "SBOM catalog may miss dependencies referenced only dynamically in vendored code.",
            "No installed ML, Agents, GPU, Wine, MT5 or broker binary inventory.",
            "Advisory matching is limited by public database coverage and CPE/purl precision.",
            "No license legal opinion, code-execution safety claim, secret scan or penetration test.",
            "No GitHub plan change or automatic third-party update.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    result = generate(args.directory, args.commit)
    output = args.directory / "triage_summary.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for name, info in result["scans"].items():
        print(name, "components:", info["sbom_components"],
              "advisory findings:", info["findings"]["total"])
    print("REVIEW REQUIRED: no G0 acceptance or trading permission")


if __name__ == "__main__":
    main()

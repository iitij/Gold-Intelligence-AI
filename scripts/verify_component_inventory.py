"""Verify exact, deterministic *preliminary* component inventory against committed locks.

Does not execute vendor code or claim a completed security review. A dated scoped scan exists.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def derive_inventory(root: Path = ROOT) -> dict:
    text = (root / "requirements-ci.lock").read_text(encoding="utf-8")
    packages = []
    for section in re.split(r"(?=^[A-Za-z0-9_-]+==)", text, flags=re.MULTILINE):
        match = re.match(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", section)
        if match is None:
            continue
        packages.append({
            "name": match.group(1),
            "version": match.group(2),
            "sha256_hash_count": section.count("--hash=sha256:"),
        })
    full = json.loads((root / "vendor/SNAPSHOT_MANIFEST.json").read_text())
    refs = json.loads((root / "vendor/RESEARCH_REFS_MANIFEST.json").read_text())
    models = json.loads((root / "models/foundation_weights.lock.json").read_text())
    return {
        "schema_version": 1,
        "as_of": "2026-11-08",
        "classification": "PRELIMINARY_COMPONENT_INVENTORY_NOT_A_COMPLETE_SBOM",
        "cve_scan_performed": True,
        "cve_scan_scope": (
            "Dated Python 3.11 CI bootstrap environment and identifiable locked "
            "vendor source dependency metadata only"
        ),
        "cve_scan_final_review_completed": False,
        "cve_scan_reference": (
            "planning/security/scans/one_time/triage_classification.json"
        ),
        "licenses_transitive_reviewed": False,
        "external_update_policy": "immutable_reviewed_sources_no_auto_refresh",
        "ci_python_3_11_packages": packages,
        "vendor_frozen_sources": [{
            "repository": x["repository"], "revision": x["commit"],
            "license": x["license_status"], "files": x["file_count"],
            "digest_sha256": x["digest_sha256"],
        } for x in full["snapshots"]],
        "review_only_repositories": [{
            "repository": x["repository"], "revision": x["commit"],
            "license": x["license"], "files": x["file_count"],
            "approved_for_runtime": False,
        } for x in refs["snapshots"]],
        "foundation_weight_revisions": [{
            "id": x["id"], "repository": x["repo_id"],
            "revision": x["revision"], "downloaded": x["downloaded"],
            "approved_for_trading": x["approved_for_trading"],
        } for x in models["assets"]],
        "not_yet_inventoried": [
            "transitive dependencies declared by the 3 archived vendor repos",
            "ML/agents optional Python dependency graphs and frozen wheels",
            "Linux OS/Wine/MetaTrader5 binaries and NVIDIA driver/CUDA",
            "licensed historical broker market data and storage artifacts",
            "Independent advisory triage/remediation, unindexed runtime components and final license/legal review",
        ],
    }


def verify() -> dict:
    expected = derive_inventory()
    actual = json.loads(
        (ROOT / "planning/security/component_inventory.json").read_text(encoding="utf-8")
    )
    if actual != expected:
        raise ValueError("Component inventory has drifted from pinned sources")
    if (not actual["cve_scan_performed"] or
        actual["cve_scan_final_review_completed"] or
        actual["licenses_transitive_reviewed"]):
        raise ValueError("Baseline scan exists, but independent review is incomplete")
    reference = ROOT / actual["cve_scan_reference"]
    if not reference.is_file():
        raise ValueError("Recorded dated advisory evidence is missing")
    if any(p["sha256_hash_count"] < 1 for p in actual["ci_python_3_11_packages"]):
        raise ValueError("Unhashed Python CI component")
    if len(actual["vendor_frozen_sources"]) != 3 or len(
        actual["review_only_repositories"]
    ) != 2:
        raise ValueError("Incomplete fixed source inventory")
    return actual


if __name__ == "__main__":
    out = verify()
    print("PASS: preliminary component inventory consistent;",
          len(out["ci_python_3_11_packages"]), "hash-locked Python dev packages;",
          len(out["vendor_frozen_sources"]), "pinned vendor sources;",
          "scoped CVE baseline recorded; review remains pending")

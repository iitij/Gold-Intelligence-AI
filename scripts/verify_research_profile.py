"""Verify CPU research pins, direct extras and optional installed inventory."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from verify_ci_lock import read_pins
from verify_wheelhouse import sha256

ROOT = Path(__file__).resolve().parents[1]


def validate_profile(*, installed: bool = False) -> dict[str, str]:
    pins, _ = read_pins(ROOT / "requirements-research-cpu.lock")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    for extra in ("ml", "agents"):
        for text in project["project"]["optional-dependencies"][extra]:
            requirement = Requirement(text)
            name = canonicalize_name(requirement.name)
            if name not in pins or pins[name] not in requirement.specifier:
                raise ValueError("Research lock does not satisfy declared extra: " + text)
    for lock in ("requirements-ml-baseline.lock", "requirements-build.lock"):
        constraints, _ = read_pins(ROOT / lock)
        for name, version in constraints.items():
            if name in pins and pins[name] != version:
                raise ValueError("Research lock changes an existing pin: " + name)
    build, _ = read_pins(ROOT / "requirements-build.lock")
    expected = dict(pins, **build)
    if installed:
        actual = {canonicalize_name(d.metadata["Name"]): d.version
                  for d in importlib.metadata.distributions()}
        if actual != expected:
            raise ValueError("Installed research profile differs from the combined hash locks")
    print(f"PASS: {len(pins)} locked research dependencies, {len(expected)} with bootstrap; "
          "declared ml/agents extras and existing shared versions satisfied")
    return expected


def validate_evidence(expected: dict[str, str]) -> None:
    root = ROOT / "planning/security/scans/research_cpu_2026_11_14"
    summary = json.loads((root / "summary.json").read_text())
    for name, digest in summary["input_lock_sha256"].items():
        if sha256(ROOT / name) != digest:
            raise ValueError("Archived research scan no longer describes lock: " + name)
    for name, digest in summary["artifact_sha256"].items():
        if sha256(root / name) != digest:
            raise ValueError("Archived research evidence changed: " + name)
    for name in ("research.installed.json", "licenses.metadata.json", "license_documents.json"):
        rows = json.loads((root / name).read_text())
        actual = {canonicalize_name(row["name"]): row["version"] for row in rows}
        if actual != expected:
            raise ValueError("Archived inventory differs from research locks: " + name)
    sbom = json.loads((root / "research.cdx.json").read_text())
    scan = json.loads((root / "research.grype.json").read_text())
    docs = json.loads((root / "license_documents.json").read_text())
    if (len(sbom["components"]) != summary["components"] or
            len(scan["matches"]) != summary["matches"] or
            len(scan.get("ignoredMatches", [])) != summary["ignored_matches"] or
            len(expected) != summary["distributions"] or
            sum(len(row["documents"]) for row in docs) != summary["license_documents"] or
            scan["descriptor"]["db"]["status"] != summary["database"] or
            not summary["database"]["valid"]):
        raise ValueError("Inconsistent archived research scan summary")
    print(f"PASS: archived research scan: {summary['components']} components, "
          f"{summary['matches']} matches; {summary['license_documents']} license documents")
    print("Historical package evidence only; complete redistribution/data acceptance not granted")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed", action="store_true")
    parser.add_argument("--evidence", action="store_true")
    args = parser.parse_args()
    expected = validate_profile(installed=args.installed)
    if args.evidence:
        validate_evidence(expected)

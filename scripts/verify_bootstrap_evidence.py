"""Verify archived package scan provenance; this does not perform a fresh CVE scan."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from verify_ci_lock import read_pins

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "planning/security/scans/bootstrap_2026_11_14"


def main() -> None:
    summary = json.loads((EVIDENCE / "summary.json").read_text())
    for name, expected in summary["input_lock_sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Scan no longer describes lock: " + name)
    build, _ = read_pins(ROOT / "requirements-build.lock")
    for profile, info in summary["profiles"].items():
        for name, expected in info["artifacts"].items():
            if hashlib.sha256((EVIDENCE / name).read_bytes()).hexdigest() != expected:
                raise ValueError("Archived scan artifact changed: " + name)
        lock = "requirements-ci.lock" if profile == "ci" else "requirements-ml-baseline.lock"
        pins, _ = read_pins(ROOT / lock)
        for name, version in build.items():
            if name in pins and pins[name] != version:
                raise ValueError("Bootstrap/profile lock conflict: " + name)
            pins[name] = version
        installed = json.loads((EVIDENCE / f"{profile}.installed.json").read_text())
        actual = {p["name"].lower().replace("_", "-"): p["version"] for p in installed}
        if actual != pins:
            raise ValueError("Installed inventory differs from locks: " + profile)
        sbom = json.loads((EVIDENCE / f"{profile}.cdx.json").read_text())
        scan = json.loads((EVIDENCE / f"{profile}.grype.json").read_text())
        if (len(sbom["components"]) != info["components"] or
                len(scan["matches"]) != info["matches"] or
                len(scan.get("ignoredMatches", [])) != info["ignored_matches"] or
                scan["descriptor"]["db"]["status"] != info["database"] or
                not info["database"]["valid"]):
            raise ValueError("Inconsistent archived scan summary: " + profile)
        print(f"PASS: archived {profile} scan, {info['components']} components, "
              f"{info['matches']} matches; DB built {info['database']['built']}")
    print("Historical evidence only; full license, OS and training gates remain blocked")


if __name__ == "__main__":
    main()

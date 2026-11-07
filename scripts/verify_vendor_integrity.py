"""Verify immutable curated vendor sources against exact Git blob identifiers.

Runs locally and in CI. Never reaches the network or upgrades upstream sources.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = Path("sources/frozen_vendor.lock.json")
VENDOR = Path("vendor/frozen_2026_11_07")


class VendorIntegrityError(ValueError):
    pass


def git_blob_sha1(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


def verify_vendor(root: Path = ROOT) -> int:
    data = json.loads((root / LOCK).read_text(encoding="utf-8"))
    if data["freeze_policy"] != "immutable-baseline-no-upstream-sync":
        raise VendorIntegrityError("Baseline is not immutable")
    rows = data["entries"]
    if not rows or len({r["path"] for r in rows}) != len(rows):
        raise VendorIntegrityError("Missing or duplicated source paths")
    accounted = set()
    for entry in rows:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts or not relative.is_relative_to(VENDOR):
            raise VendorIntegrityError("Unsafe or unexpected source path")
        target = root / relative
        if not target.is_file() or target.is_symlink():
            raise VendorIntegrityError(f"Missing or symlinked frozen file: {relative}")
        if git_blob_sha1(target.read_bytes()) != entry["git_blob_sha1"]:
            raise VendorIntegrityError(f"Frozen source modified: {relative}")
        accounted.add(relative.as_posix())
    actual = {
        p.relative_to(root).as_posix()
        for p in (root / VENDOR).rglob("*")
        if p.is_file()
        and p.relative_to(root).as_posix() != f"{VENDOR.as_posix()}/README.md"
        and "__pycache__" not in p.parts
        and p.suffix != ".pyc"
    }
    if actual != accounted:
        raise VendorIntegrityError(f"Unreviewed frozen files: {sorted(actual - accounted)}")
    return len(rows)


if __name__ == "__main__":
    print("Verified", verify_vendor(), "immutable frozen source files")

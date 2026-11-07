"""Offline verification for optional, untrusted research-reference archive.

Never imports or executes archived software.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify_archive(root: Path = ROOT) -> int:
    lock = json.loads(
        (root / "sources/research_candidates_2026_11_08.lock.json").read_text()
    )
    registry = {c["repository"]: c for c in lock["candidates"]
                if c["decision"] == "one-time-offline-review"}
    archive = root / "vendor/research_refs"
    manifest_file = root / "vendor/RESEARCH_REFS_MANIFEST.json"
    if not archive.exists() and not manifest_file.exists():
        return 0  # Before the one-time GitHub Actions archive is merged.
    if not archive.is_dir() or not manifest_file.is_file():
        raise ValueError("Partial research archive")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if (manifest.get("sealed") is not True or
        manifest.get("policy") != "offline-reference-only-no-execution-no-upstream-sync"):
        raise ValueError("Unexpected archive policy")
    rows = manifest.get("snapshots", [])
    if len(rows) != len(registry) or {r["repository"] for r in rows} != set(registry):
        raise ValueError("Missing/unapproved research sources")
    expected_dirs = {name.replace("/", "--") for name in registry}
    if {x.name for x in archive.iterdir()} != expected_dirs:
        raise ValueError("Unregistered directory")
    total = 0
    for row in rows:
        record = registry[row["repository"]]
        if any([
            row["commit"] != record["commit"],
            row["license"] != record["license"],
            row.get("archive_only") is not True,
            row.get("runtime_approved") is not False,
            row.get("upstream_sync_allowed") is not False,
        ]):
            raise ValueError("Untrusted source provenance mismatch")
        origin = archive / row["repository"].replace("/", "--")
        digest = hashlib.sha256()
        count = 0
        byte_count = 0
        for path in sorted(origin.rglob("*")):
            if path.is_symlink():
                raise ValueError("Symlink not allowed in research archive")
            if not path.is_file():
                continue
            rel = path.relative_to(origin).as_posix()
            data = path.read_bytes()
            digest.update(rel.encode() + b"\0" + hashlib.sha256(data).digest())
            byte_count += len(data)
            count += 1
        if (count != row["file_count"] or byte_count != row["total_bytes"] or
            digest.hexdigest() != row["digest_sha256"]):
            raise ValueError("Reference code modified or missing: " + row["repository"])
        total += count
    return total


if __name__ == "__main__":
    print("Verified review-only archive file count:", verify_archive())

"""Offline validation of the one-time complete source archive and model revisions.

This script reads bytes and hashes only. It never imports/executes external code.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = Path("vendor/snapshots")
MANIFEST = Path("vendor/SNAPSHOT_MANIFEST.json")
SOURCE_LOCK = Path("sources/sources.lock.json")
MODEL_CANDIDATES = Path("models/foundation_candidates.json")
MODEL_LOCK = Path("models/foundation_weights.lock.json")
SHA40 = re.compile(r"^[a-f0-9]{40}$")
FORBIDDEN_KEYS = [
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"ghp_[A-Za-z0-9]{36}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{40,}"),
]


class SnapshotIntegrityError(ValueError):
    pass


def verify_all(root: Path = ROOT) -> tuple[int, int]:
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    source_lock = json.loads((root / SOURCE_LOCK).read_text(encoding="utf-8"))
    model_lock = json.loads((root / MODEL_LOCK).read_text(encoding="utf-8"))
    candidates = json.loads((root / MODEL_CANDIDATES).read_text(encoding="utf-8"))
    if not manifest.get("sealed") or manifest.get("upstream_updates_allowed") is not False:
        raise SnapshotIntegrityError("Upstream snapshots are not sealed")
    allowed = {
        row["repository"]: row
        for row in source_lock["sources"]
        if row["mode"] in {"snapshot-approved", "snapshot-optional"}
    }
    if {row["repository"] for row in manifest["snapshots"]} != set(allowed):
        raise SnapshotIntegrityError("Unexpected/missing source archive")
    if len(manifest["snapshots"]) != len(allowed):
        raise SnapshotIntegrityError("Duplicate source archives")
    archive = root / ARCHIVE
    actual_names = {p.name for p in archive.iterdir() if p.is_dir()}
    expected_names = {name.replace("/", "--") for name in allowed}
    if actual_names != expected_names:
        raise SnapshotIntegrityError("Unregistered directory in snapshot archive")
    total_files = 0
    for item in manifest["snapshots"]:
        source = allowed[item["repository"]]
        if source["license_status"] not in {"Apache-2.0", "MIT"}:
            raise SnapshotIntegrityError("Disallowed source license")
        if item["commit"] != source["commit"] or item["license_status"] != source["license_status"]:
            raise SnapshotIntegrityError("Source provenance mismatch")
        if not SHA40.fullmatch(item["commit"]):
            raise SnapshotIntegrityError("Invalid source SHA")
        directory = archive / item["repository"].replace("/", "--")
        if not directory.is_dir() or directory.is_symlink():
            raise SnapshotIntegrityError("Missing/invalid archive directory")
        license_exists = any(
            (directory / filename).is_file()
            for filename in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")
        )
        if not license_exists:
            raise SnapshotIntegrityError("Source license missing")
        digest = hashlib.sha256()
        count = 0
        for file in sorted(directory.rglob("*")):
            if file.is_symlink():
                raise SnapshotIntegrityError("Symlink in source archive")
            if not file.is_file():
                continue
            rel = file.relative_to(directory)
            if ".git" in rel.parts:
                raise SnapshotIntegrityError("Unexpected Git metadata")
            if file.name.startswith(".env") and not file.name.endswith(".example"):
                raise SnapshotIntegrityError("Secret environment file in archive")
            data = file.read_bytes()
            if any(pattern.search(data) for pattern in FORBIDDEN_KEYS):
                raise SnapshotIntegrityError("Potential credential/private key in " + str(rel))
            digest.update(rel.as_posix().encode("utf-8") + b"\0" +
                          hashlib.sha256(data).digest())
            count += 1
        if count != item["file_count"] or digest.hexdigest() != item["digest_sha256"]:
            raise SnapshotIntegrityError("Snapshot digest/count mismatch: " + item["repository"])
        total_files += count

    expected = {entry["id"]: entry for entry in candidates["candidates"]}
    assets = model_lock["assets"]
    if model_lock.get("policy") != "immutable-no-upstream-refresh; metadata-only; no weights included":
        raise SnapshotIntegrityError("Unexpected model update policy")
    if len(assets) != len(expected) or len({x["id"] for x in assets}) != len(expected):
        raise SnapshotIntegrityError("Missing or duplicated model entries")
    for asset in assets:
        source = expected.get(asset["id"])
        if not source:
            raise SnapshotIntegrityError("Unknown model")
        if asset["repo_id"] != source["repo_id"]:
            raise SnapshotIntegrityError("Wrong model repository")
        if asset["license_expected"] != source["license_expected"]:
            raise SnapshotIntegrityError("Model license mismatch")
        if not asset["license_verified_via_api"]:
            raise SnapshotIntegrityError("Model license metadata not verified")
        if not SHA40.fullmatch(asset.get("revision", "")):
            raise SnapshotIntegrityError("Unpinned model revision")
        files = asset["files_expected_safetensors"]
        if not files or any(not name.endswith(".safetensors") for name in files):
            raise SnapshotIntegrityError("Missing or unsafe weight file names")
        if asset["downloaded"] or asset["approved_for_trading"]:
            raise SnapshotIntegrityError("Incorrect model deployment status")
    return total_files, len(assets)


if __name__ == "__main__":
    files, models = verify_all()
    print("PASS:", files, "frozen source files and", models, "pinned model revisions")

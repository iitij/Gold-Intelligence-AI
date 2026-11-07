"""Explicit, offline-verifiable model asset management. Never auto-update."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "models/foundation_candidates.json"
LOCK = ROOT / "models/foundation_weights.lock.json"
WEIGHTS = ROOT / "models/weights"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
ALLOWED_PATTERNS = [
    "*.safetensors",
    "*.json",
    "*.txt",
    "*.model",
    "*.jinja",
    "README.md",
    "LICENSE",
    "merges.txt",
    "vocab.json",
    "tokenizer.json",
]


def load_lock() -> dict:
    if not LOCK.is_file():
        raise ValueError("No pinned model lock. Run pin_models_once.py first.")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    if lock.get("policy") != "immutable-no-upstream-refresh; metadata-only; no weights included":
        raise ValueError("Unrecognized model lock policy")
    if not lock.get("assets"):
        raise ValueError("Empty model lock")
    for item in lock["assets"]:
        if not SHA40.fullmatch(item.get("revision", "")):
            raise ValueError("Model revision must be exactly pinned")
    return lock


def list_models() -> None:
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    for item in candidates["candidates"]:
        print(item["id"], "|", item["repo_id"], "|", item["status"])
    for item in candidates["train_from_scratch"]:
        print(item["id"], "|", item["framework"], "|", item["status"])


def file_hashes(root: Path) -> list[dict]:
    results = []
    for file in sorted(root.rglob("*")):
        if not file.is_file():
            continue
        relative = file.relative_to(root).as_posix()
        if relative == "artifact_manifest.json" or relative.startswith(".cache/"):
            continue
        digest = hashlib.sha256()
        with file.open("rb") as stream:
            while chunk := stream.read(4 * 1024 * 1024):
                digest.update(chunk)
        results.append({"path": relative, "size_bytes": file.stat().st_size,
                        "sha256": digest.hexdigest()})
    return results


def get_asset(model_id: str) -> dict:
    items = [item for item in load_lock()["assets"] if item["id"] == model_id]
    if len(items) != 1:
        raise ValueError("Unknown model id: " + model_id)
    return items[0]


def verify(model_id: str) -> int:
    asset = get_asset(model_id)
    folder = WEIGHTS / model_id
    manifest_path = folder / "artifact_manifest.json"
    if not manifest_path.exists():
        raise ValueError("Model not downloaded locally")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["revision"] != asset["revision"] or manifest["repo_id"] != asset["repo_id"]:
        raise ValueError("Wrong model identity or revision")
    actual = file_hashes(folder)
    if actual != manifest["files"]:
        raise ValueError("Corrupted, added, or missing model files")
    return len(actual)


def download(model_id: str) -> None:
    asset = get_asset(model_id)
    target = WEIGHTS / model_id
    if target.exists():
        raise ValueError("Model directory already exists; refuse to overwrite")
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError("Install huggingface_hub separately for deliberate downloads") from exc
    WEIGHTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".model-stage-", dir=WEIGHTS) as temp:
        stage = Path(temp)
        snapshot_download(repo_id=asset["repo_id"], revision=asset["revision"],
                          local_dir=str(stage), allow_patterns=ALLOWED_PATTERNS)
        shutil.rmtree(stage / ".cache", ignore_errors=True)
        entries = file_hashes(stage)
        if not entries:
            raise ValueError("No model files downloaded")
        present = {f["path"] for f in entries}
        if not set(asset["files_expected_safetensors"]).issubset(present):
            raise ValueError("Missing required safetensors shards")
        manifest = {
            "repo_id": asset["repo_id"],
            "revision": asset["revision"],
            "sha256_algorithm": "sha256",
            "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "files": entries,
        }
        (stage / "artifact_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        stage.rename(target)
    print("Downloaded and hashed:", model_id)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["list", "download", "verify"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if args.command == "list":
        list_models()
        return
    if not args.model:
        parser.error("--model is required")
    if args.command == "download":
        if not args.confirm:
            parser.error("--confirm is required before downloading large model weights")
        download(args.model)
    else:
        print("Verified", verify(args.model), "files for", args.model)


if __name__ == "__main__":
    main()

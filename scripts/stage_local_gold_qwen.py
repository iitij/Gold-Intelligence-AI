"""Verify the pinned Qwen manifest and blobs before installing them in a local Ollama store."""

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from goldintel.agents.ollama import MODEL_DIGEST

MODEL_WEIGHT = "application/vnd.ollama.image.model"
MANIFEST_PATH = Path("manifests/registry.ollama.ai/library/qwen3/4b-q4_K_M")


def file_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def install_verified(path, target, digest):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if file_digest(target) != digest:
            raise ValueError(f"Existing Ollama file does not match: {target.name}")
        return
    # Copy to the target filesystem. Later changes to the download cannot alter the store.
    with tempfile.NamedTemporaryFile(dir=target.parent) as staged:
        with path.open("rb") as stream:
            shutil.copyfileobj(stream, staged)
        staged.flush()
        if file_digest(Path(staged.name)) != digest:
            raise ValueError(f"Staged Ollama file does not match: {target.name}")
        try:
            os.link(staged.name, target)
        except FileExistsError:
            if file_digest(target) != digest:
                raise ValueError(f"Concurrent Ollama file does not match: {target.name}") from None


def stage(source, destination):
    candidate = source / "qwen3-4b-manifest.json"
    raw = candidate.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MODEL_DIGEST:
        raise ValueError("Qwen manifest does not match the repository digest")
    manifest = json.loads(raw)
    blobs = []
    for entry in [manifest["config"], *manifest["layers"]]:
        digest = entry["digest"].removeprefix("sha256:")
        filename = f"sha256-{digest}"
        path = source / ("qwen3-4b-weights" if entry["mediaType"] == MODEL_WEIGHT else filename)
        if path.stat().st_size != entry["size"] or file_digest(path) != digest:
            raise ValueError(f"Blob fails size or SHA256 verification: {filename}")
        blobs.append((path, destination / "blobs" / filename, digest))
    for path, target, digest in blobs:
        install_verified(path, target, digest)
    install_verified(candidate, destination / MANIFEST_PATH, MODEL_DIGEST)
    print(f"Verified {len(blobs)} blobs and Qwen manifest {MODEL_DIGEST}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path, help="Local Ollama model store")
    args = parser.parse_args()
    stage(args.source, args.destination)


if __name__ == "__main__":
    main()

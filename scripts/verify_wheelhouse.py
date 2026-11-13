"""Check a retained wheelhouse against its manifest; authenticity is external."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(path: Path) -> None:
    manifest = json.loads((path / "WHEELHOUSE.json").read_text())
    files = manifest["files"]
    if manifest.get("schema_version") != 1 or not files:
        raise ValueError("Invalid wheelhouse manifest")
    if any(name in {".", "..", "WHEELHOUSE.json"} or Path(name).name != name for name in files):
        raise ValueError("Manifest filenames must be plain local names")
    if {p.name for p in path.iterdir()} != set(files) | {"WHEELHOUSE.json"}:
        raise ValueError("Wheelhouse contains missing or unexpected files")
    for name, expected in files.items():
        file = path / name
        if file.is_symlink() or not file.is_file() or sha256(file) != expected:
            raise ValueError("Wheelhouse file failed integrity check: " + name)
    print(f"PASS: {len(files)} retained wheelhouse files match their manifest")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    validate(parser.parse_args().path)

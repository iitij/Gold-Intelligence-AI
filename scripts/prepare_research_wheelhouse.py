"""Download exact CPU wheels and stage a manifest for retained CI artifacts."""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

from verify_wheelhouse import sha256, validate

ROOT = Path(__file__).resolve().parents[1]
LOCKS = ("requirements-build.lock", "requirements-research-cpu.lock")


def main(output: Path) -> None:
    if output.exists():
        raise ValueError("Refusing to overwrite an existing wheelhouse")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gold-wheelhouse-", dir=output.parent) as temp:
        stage = Path(temp)
        subprocess.run([sys.executable, "-m", "pip", "download", "--require-hashes",
                        "--only-binary=:all:", "-r", LOCKS[0], "-r", LOCKS[1],
                        "-d", str(stage)], cwd=ROOT, check=True)
        for lock in LOCKS:
            shutil.copyfile(ROOT / lock, stage / lock)
        licenses = ROOT / "planning/security/scans/research_cpu_2026_11_14"
        for name in ("catboost-upstream-LICENSE.txt", "flask-cors-upstream-LICENSE.txt",
                     "license_review.json", "license_documents.json", "licenses.metadata.json"):
            shutil.copyfile(licenses / name, stage / name)
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                           text=True).strip()
        (stage / "OFFLINE-INSTALL.txt").write_text(
            "CPU research wheels only; no OS, interpreter, model or market data.\n"
            f"Source revision: {revision}\n"
            "Authenticate the downloaded artifact via its GitHub Actions digest.\n"
            "From that checkout, verify with:\n"
            "python scripts/verify_wheelhouse.py /path/to/unpacked-wheelhouse\n"
            "Use Linux x86_64 and the Python ABI recorded in WHEELHOUSE.json.\n"
            "Create a seedless target venv outside this directory, then use an\n"
            "existing trusted pip (supports --python) to install into it:\n"
            "python -m pip --python /path/to/target install --no-index "
            "--find-links /path/to/unpacked-wheelhouse --require-hashes "
            "--only-binary=:all: -r /path/to/unpacked-wheelhouse/requirements-build.lock "
            "-r /path/to/unpacked-wheelhouse/requirements-research-cpu.lock\n"
            "This does not grant data acceptance, training or trading approval.\n")
        manifest = {
            "schema_version": 1, "source_revision": revision,
            "source_tree_dirty": bool(subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()),
            "python": sys.version, "platform": platform.platform(),
            "python_platform": sysconfig.get_platform(), "soabi": sysconfig.get_config_var("SOABI"),
            "files": {p.name: sha256(p) for p in sorted(stage.iterdir())},
        }
        (stage / "WHEELHOUSE.json").write_text(json.dumps(manifest, indent=2) + "\n")
        validate(stage)
        os.rename(stage, output)
    print(f"PASS: staged {len(list(output.glob('*.whl')))} wheels at {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "artifacts/research-cpu-wheelhouse")
    main(parser.parse_args().output.resolve())

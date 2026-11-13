"""Reinstall the reviewed CI wheels in a fresh venv without an index.

This checks Python package reuse, not OS/interpreter reproducibility.
The wheel download is online; only the subsequent installation is offline.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    subprocess.run(args, check=True, cwd=ROOT)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="gold-ci-reinstall-") as tmp:
        root = Path(tmp)
        wheels = root / "wheels"
        target = root / "venv"
        run(sys.executable, "-m", "pip", "download", "--require-hashes",
            "--only-binary=:all:", "-r", "requirements-ci.lock", "-r", "requirements-build.lock", "-d", str(wheels))
        venv.EnvBuilder(with_pip=False).create(target)
        python = str(target / "bin" / "python")
        run(sys.executable, "-m", "pip", "--python", python, "install", "--no-index",
            "--find-links", str(wheels), "--require-hashes", "--only-binary=:all:",
            "-r", "requirements-ci.lock", "-r", "requirements-build.lock")
        run(sys.executable, "-m", "pip", "--python", python, "check")
        inventory = subprocess.check_output(
            [sys.executable, "-m", "pip", "--python", python, "list", "--format=json"],
            text=True,
        )
        print(json.dumps({"python": sys.version, "installed": json.loads(inventory)}, indent=2))
        run(python, "-m", "pytest", "-q")
        run(python, "-m", "ruff", "check", "src", "tests", "scripts")
        print("PASS: hash-locked CI wheels reinstalled and tested without an index")


if __name__ == "__main__":
    main()

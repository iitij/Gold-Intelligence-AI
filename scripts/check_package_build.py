"""Compare two wheel builds from separate source copies with locked local tools."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    env = dict(os.environ, SOURCE_DATE_EPOCH="315532800", PIP_NO_INDEX="1")
    hashes = []
    inputs = {}
    with tempfile.TemporaryDirectory(prefix="gold-wheel-build-") as temp:
        base = Path(temp)
        for index in range(2):
            source = base / str(index)
            source.mkdir()
            shutil.copytree(ROOT / "src", source / "src",
                            ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
            shutil.copy2(ROOT / "pyproject.toml", source / "pyproject.toml")
            if index == 0:
                inputs = {str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sorted(source.rglob("*")) if path.is_file()}
            subprocess.run([sys.executable, "-m", "build", "--wheel", "--no-isolation"],
                           cwd=source, env=env, check=True)
            wheels = list((source / "dist").glob("*.whl"))
            if len(wheels) != 1:
                raise RuntimeError("Expected exactly one built wheel")
            wheel = wheels[0]
            hashes.append(hashlib.sha256(wheel.read_bytes()).hexdigest())
        if hashes[0] != hashes[1]:
            raise RuntimeError(f"Wheel builds differ: {hashes}")
        target = base / "installed"
        venv.EnvBuilder(with_pip=False).create(target)
        python = str(target / "bin/python")
        subprocess.run([sys.executable, "-m", "pip", "--python", python, "install",
                        "--no-index", "--no-deps", str(wheel)], check=True, env=env)
        subprocess.run([python, "-I", "-c",
                        "import goldintel; from importlib.metadata import version; "
                        "assert version('gold-intelligence-ai') == '0.1.0a0'; "
                        "print('PASS: isolated wheel import', goldintel.__file__)"],
                       check=True, cwd=base, env=env)
    evidence = {
        "python": sys.version, "platform": platform.platform(),
        "source_date_epoch": env["SOURCE_DATE_EPOCH"], "wheel_sha256": hashes,
        "input_sha256": inputs,
        "tools": {name: importlib.metadata.version(name)
                  for name in ("pip", "setuptools", "wheel", "build", "packaging",
                               "pyproject-hooks")},
        "scope": "two local source copies; no build isolation or index; core wheel only",
    }
    path = ROOT / "artifacts/build-reproducibility.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    print("PASS: byte-identical core wheel builds and isolated installed import")


if __name__ == "__main__":
    main()

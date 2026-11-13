"""Verify immutable Python CI wheel hashes and pinned Actions before tests.

This checks structure only, not CVEs, licensing, or wheel authenticity.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "requirements-ci.lock"
WORKFLOW = ROOT / ".github/workflows/ci.yml"
HASH = re.compile(r"--hash=sha256:[a-f0-9]{64}\b")
PACKAGE = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)")


def read_pins(path: Path) -> tuple[dict[str, str], int]:
    lines = path.read_text(encoding="utf-8").splitlines()
    entries = []
    current = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if PACKAGE.match(line) and current:
            entries.append("\n".join(current))
            current = []
        if stripped.startswith("--hash=") and not current:
            raise ValueError("Hash without package")
        current.append(line)
    if current:
        entries.append("\n".join(current))
    pkgs = {}
    hashes = 0
    for entry in entries:
        head = PACKAGE.match(entry)
        if not head:
            raise ValueError("Non-pinned requirement")
        name = head.group(1).lower().replace("_", "-")
        if name in pkgs:
            raise ValueError("Duplicate pinned package")
        found = HASH.findall(entry)
        if not found:
            raise ValueError("No SHA256 wheel hash for " + name)
        pkgs[name] = head.group(2)
        hashes += len(found)
    return pkgs, hashes


def validate_build_lock(root: Path = ROOT) -> None:
    pins, _ = read_pins(root / "requirements-build.lock")
    if not {"pip", "setuptools", "wheel", "build", "packaging", "pyproject-hooks"} <= pins.keys():
        raise ValueError("Missing locked bootstrap/build dependencies")
    project = tomllib.loads((root / "pyproject.toml").read_text())
    expected = {f"setuptools=={pins['setuptools']}", f"wheel=={pins['wheel']}"}
    if set(project["build-system"]["requires"]) != expected:
        raise ValueError("Build requirements differ from bootstrap lock")
    for name in ("ci.yml", "ml-baseline.yml"):
        workflow = (root / ".github/workflows" / name).read_text()
        if ("python -m venv --without-pip .venv" not in workflow or
                "--require-hashes --only-binary=:all: -r requirements-build.lock" not in workflow):
            raise ValueError("Workflow lacks isolated locked bootstrap: " + name)


def validate_lock() -> tuple[int, int]:
    pkgs, hashes = read_pins(LOCK)
    validate_build_lock()
    if not {"pytest", "ruff"}.issubset(pkgs):
        raise ValueError("Missing core test/lint dependency")
    if len(pkgs) < 2 or hashes < len(pkgs):
        raise ValueError("Incomplete hash inventory")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    if "pip install --require-hashes -r requirements-ci.lock" not in workflow:
        raise ValueError("CI does not install from hashes")
    if "pip install -e '.[dev]'" in workflow:
        raise ValueError("CI still resolves unpinned packages")
    if not re.search(r"actions/checkout@[a-f0-9]{40}", workflow) or not re.search(
        r"actions/setup-python@[a-f0-9]{40}", workflow
    ):
        raise ValueError("GitHub Actions must be commit-pinned")
    return len(pkgs), hashes


if __name__ == "__main__":
    n, hashes = validate_lock()
    print(f"PASS: {n} exact Python CI dependency pins, {hashes} allowed SHA256 hashes")

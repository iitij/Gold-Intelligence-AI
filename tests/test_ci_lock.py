"""Dependency lock must never silently resolve floating package versions."""
from pathlib import Path

import pytest

from scripts.verify_ci_lock import validate_build_lock, validate_lock

ROOT = Path(__file__).resolve().parents[1]


def test_ci_uses_immutable_hash_deps_and_commit_pinned_actions():
    packages, hashes = validate_lock()
    assert packages >= 2
    assert hashes >= packages


def test_one_time_resolver_workflow_retired():
    assert not (ROOT / ".github/workflows/generate-ci-lock-once.yml").exists()


def test_no_broker_secrets_or_model_weights_in_ci_dependencies():
    lock = (ROOT / "requirements-ci.lock").read_text()
    assert "MetaTrader5==" not in lock
    assert "huggingface-hub==" not in lock
    assert "torch==" not in lock


def test_build_backend_cannot_drift_from_hash_lock(tmp_path):
    for name in ("requirements-build.lock", "pyproject.toml"):
        (tmp_path / name).write_bytes((ROOT / name).read_bytes())
    workflows = tmp_path / ".github/workflows"
    workflows.mkdir(parents=True)
    for name in ("ci.yml", "ml-baseline.yml"):
        (workflows / name).write_bytes((ROOT / ".github/workflows" / name).read_bytes())
    validate_build_lock(tmp_path)
    project = tmp_path / "pyproject.toml"
    project.write_text(project.read_text().replace("setuptools==84.2.1", "setuptools>=69"))
    with pytest.raises(ValueError, match="Build requirements differ"):
        validate_build_lock(tmp_path)

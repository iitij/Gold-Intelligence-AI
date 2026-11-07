"""Dependency lock must never silently resolve floating package versions."""
from pathlib import Path

from scripts.verify_ci_lock import validate_lock

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

"""Owner scope excludes license triage while keeping technical provenance checks."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def policy_root(tmp_path):
    (tmp_path / ".env.example").write_bytes((ROOT / ".env.example").read_bytes())
    (tmp_path / "sources").mkdir()
    (tmp_path / "src/goldintel").mkdir(parents=True)
    (tmp_path / "src/goldintel/__init__.py").write_text("SAFE = True\n")
    return tmp_path


@pytest.mark.parametrize("commit,allowed", [("a" * 40, True), ("floating-main", False)])
def test_unreviewed_license_does_not_block_but_unpinned_source_does(
        policy_root, monkeypatch, commit, allowed):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    from check_repository_policy import CoreSafetyViolation, check_policy

    (policy_root / "sources/sources.lock.json").write_text(json.dumps({"sources": [{
        "commit": commit, "mode": "snapshot-approved", "license_status": "not-reviewed",
    }]}))
    if allowed:
        check_policy(policy_root)
    else:
        with pytest.raises(CoreSafetyViolation, match="Unpinned source SHA"):
            check_policy(policy_root)

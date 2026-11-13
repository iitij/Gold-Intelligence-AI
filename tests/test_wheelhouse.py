"""Retained artifact integrity must fail on corruption and incomplete downloads."""
import hashlib
import json

import pytest

from scripts.verify_wheelhouse import validate


@pytest.fixture
def wheelhouse(tmp_path):
    data = b"synthetic artifact integrity fixture, not a usable wheel"
    (tmp_path / "fixture.whl").write_bytes(data)
    (tmp_path / "WHEELHOUSE.json").write_text(json.dumps({
        "schema_version": 1, "files": {"fixture.whl": hashlib.sha256(data).hexdigest()},
    }))
    return tmp_path


def test_complete_artifact_matches_manifest(wheelhouse):
    validate(wheelhouse)


def test_corrupt_download_is_rejected(wheelhouse):
    (wheelhouse / "fixture.whl").write_bytes(b"truncated")
    with pytest.raises(ValueError, match="integrity"):
        validate(wheelhouse)


def test_missing_wheel_is_rejected(wheelhouse):
    (wheelhouse / "fixture.whl").unlink()
    with pytest.raises(ValueError, match="missing"):
        validate(wheelhouse)


def test_stale_extra_wheel_is_rejected(wheelhouse):
    (wheelhouse / "stale.whl").write_bytes(b"old dependency")
    with pytest.raises(ValueError, match="unexpected"):
        validate(wheelhouse)

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


@pytest.mark.parametrize("revision,dirty", [("b" * 40, False), ("a" * 40, True)])
def test_artifact_from_wrong_or_modified_checkout_is_rejected(wheelhouse, revision, dirty):
    path = wheelhouse / "WHEELHOUSE.json"
    manifest = json.loads(path.read_text())
    manifest.update(source_revision=revision, source_tree_dirty=dirty)
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="source revision"):
        validate(wheelhouse, expected_revision="a" * 40)


def test_matching_clean_source_revision_is_verified(wheelhouse):
    path = wheelhouse / "WHEELHOUSE.json"
    manifest = json.loads(path.read_text())
    manifest.update(source_revision="a" * 40, source_tree_dirty=False)
    path.write_text(json.dumps(manifest))
    validate(wheelhouse, expected_revision="a" * 40)

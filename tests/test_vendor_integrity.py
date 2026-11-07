"""Pure synthetic tests of source integrity; no external dependency."""
import json
from pathlib import Path

import pytest

from scripts.verify_vendor_integrity import VendorIntegrityError, git_blob_sha1, verify_vendor


def fixture_vendor(tmp_path: Path):
    relative = Path("vendor/frozen_2026_11_07/aurum/LICENSE")
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(b"synthetic MIT license test fixture\n")
    lock = tmp_path / "sources/frozen_vendor.lock.json"
    lock.parent.mkdir(parents=True)
    lock.write_text(
        json.dumps({
            "freeze_policy": "immutable-baseline-no-upstream-sync",
            "entries": [{"path": relative.as_posix(), "git_blob_sha1": git_blob_sha1(target.read_bytes())}],
        }),
        encoding="utf-8",
    )
    return target


def test_exact_bytes_pass(tmp_path):
    fixture_vendor(tmp_path)
    assert verify_vendor(tmp_path) == 1


def test_tamper_detected(tmp_path):
    target = fixture_vendor(tmp_path)
    target.write_bytes(target.read_bytes() + b"tampered")
    with pytest.raises(VendorIntegrityError, match="modified"):
        verify_vendor(tmp_path)


def test_unrecorded_file_detected(tmp_path):
    target = fixture_vendor(tmp_path)
    (target.parent / "unreviewed.py").write_text("pass", encoding="utf-8")
    with pytest.raises(VendorIntegrityError, match="Unreviewed"):
        verify_vendor(tmp_path)


def test_known_git_blob_digest():
    assert git_blob_sha1(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"

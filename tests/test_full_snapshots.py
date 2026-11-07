"""Tamper detection and pinning invariants for the complete third-party archive."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_complete_archive_passes_integrity_validation():
    proc = subprocess.run(
        [sys.executable, "scripts/verify_full_snapshots.py"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    assert "PASS:" in proc.stdout
    assert "584 frozen source files" in proc.stdout
    assert "3 pinned model revisions" in proc.stdout


def test_snapshot_entries_match_source_allowlist():
    manifest = json.loads((ROOT / "vendor/SNAPSHOT_MANIFEST.json").read_text())
    sources = json.loads((ROOT / "sources/sources.lock.json").read_text())
    approved = {entry["repository"] for entry in sources["sources"]
                if entry["mode"] in ("snapshot-approved", "snapshot-optional")}
    assert approved == {x["repository"] for x in manifest["snapshots"]}
    assert all(x["upstream_updates_allowed"] is False for x in manifest["snapshots"])
    assert manifest["sealed"] is True


def test_no_external_weights_are_checked_in():
    assert not (ROOT / "models/weights").exists()
    pinned = json.loads((ROOT / "models/foundation_weights.lock.json").read_text())
    assert all(x["downloaded"] is False and x["approved_for_trading"] is False
               for x in pinned["assets"])

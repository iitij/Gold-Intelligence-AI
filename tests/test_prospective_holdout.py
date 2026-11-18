"""The prospective replay must not open quote data before the registered release."""
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from goldintel.research.holdout import (
    HoldoutError,
    assert_holdout_released,
    assert_no_sealed_overlap,
    read_protocol,
    verify_frozen_files,
)

START = datetime(2099, 1, 1, tzinfo=timezone.utc)
END = START + timedelta(weeks=8)
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sealed(tmp_path):
    frozen = tmp_path / "frozen"
    replay = frozen / "scripts/replay_m15_reversal.py"
    replay.parent.mkdir(parents=True)
    replay.write_bytes((ROOT / "scripts/replay_m15_reversal.py").read_bytes())
    protocol = {
        "schema_version": 1, "kind": "prospective_research_registration",
        "registered_at_utc": (START - timedelta(days=1)).isoformat(),
        "start_utc": START.isoformat(), "end_exclusive_utc": END.isoformat(),
        "frozen_files": {"scripts/replay_m15_reversal.py": hashlib.sha256(replay.read_bytes()).hexdigest()},
    }
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(protocol))
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    return path, expected, frozen, replay


def test_release_boundary_and_frozen_implementation(sealed):
    path, expected, frozen, replay = sealed
    protocol = read_protocol(path, expected)
    with pytest.raises(HoldoutError, match="sealed"):
        assert_holdout_released(protocol, now=END - timedelta(microseconds=1), start=START,
                                end=END, frozen_root=frozen, replay_path=replay)
    assert_holdout_released(protocol, now=END, start=START, end=END,
                            frozen_root=frozen, replay_path=replay)
    with pytest.raises(HoldoutError, match="interval"):
        assert_holdout_released(protocol, now=END, start=START + timedelta(days=1), end=END,
                                frozen_root=frozen, replay_path=replay)
    replay.write_text(replay.read_text() + "\n")
    with pytest.raises(HoldoutError, match="fingerprint"):
        assert_holdout_released(protocol, now=END, start=START, end=END,
                                frozen_root=frozen, replay_path=replay)


def test_protocol_anchor_and_retrospective_registration_rejected(sealed):
    path, expected, _, _ = sealed
    with pytest.raises(HoldoutError, match="fingerprint"):
        read_protocol(path, "0" * 64)
    protocol = json.loads(path.read_text())
    protocol["registered_at_utc"] = START.isoformat()
    path.write_text(json.dumps(protocol))
    with pytest.raises(HoldoutError, match="precede"):
        read_protocol(path, hashlib.sha256(path.read_bytes()).hexdigest())


def test_snapshot_path_escape_rejected(sealed):
    path, expected, frozen, _ = sealed
    protocol = read_protocol(path, expected)
    protocol["frozen_files"] = {"../outside.py": "0" * 64}
    with pytest.raises(HoldoutError, match="outside"):
        verify_frozen_files(protocol, frozen)


def test_registry_rejects_partial_or_legacy_overlapping_replay(sealed, tmp_path):
    path, expected, _, _ = sealed
    registry = tmp_path / "planning/holdout_registry.json"
    registry.parent.mkdir()
    registry.write_text(json.dumps({"schema_version": 1, "registrations": [
        {"protocol": str(path.relative_to(tmp_path)), "sha256": expected},
    ]}))
    before = START - timedelta(days=1)
    for first, last in ((before, START + timedelta(hours=1)), (START, END),
                        (START - timedelta(days=10), END - timedelta(days=2))):
        with pytest.raises(HoldoutError, match="overlaps"):
            assert_no_sealed_overlap(registry, now=before, start=first, end=last)
    assert_no_sealed_overlap(registry, now=before, start=before, end=START)
    assert_no_sealed_overlap(registry, now=END, start=START, end=END)


def test_cli_blocks_before_opening_quotes_or_creating_output(sealed, tmp_path):
    path, expected, frozen, _ = sealed
    output = tmp_path / "should-not-exist.json"
    result = subprocess.run([
        sys.executable, str(ROOT / "scripts/replay_m15_reversal.py"),
        str(tmp_path / "missing-quotes.csv"), str(output), "--start", START.isoformat(),
        "--end", END.isoformat(), "--commission-per-side-per-ounce", "0",
        "--slippage-per-side-per-ounce", "0", "--holdout-protocol", str(path),
        "--holdout-sha256", expected, "--frozen-root", str(frozen),
    ], capture_output=True, text=True, check=False, cwd=ROOT)
    assert result.returncode != 0
    assert "remains sealed" in result.stderr
    assert "FileNotFoundError" not in result.stderr
    assert not output.exists()

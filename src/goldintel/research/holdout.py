"""Time and fingerprint guard for explicitly registered prospective research windows.

This is an application guard, not an OS access-control or independent timestamp service.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from goldintel.research.point_in_time import _require_utc


class HoldoutError(ValueError):
    """A registered protocol cannot be verified or its labels are not released."""


def read_protocol(path: Path, expected_sha256: str) -> dict:
    raw = path.read_bytes()
    if (not re.fullmatch(r"[a-f0-9]{64}", expected_sha256)
            or hashlib.sha256(raw).hexdigest() != expected_sha256):
        raise HoldoutError("Holdout protocol fingerprint mismatch")
    protocol = json.loads(raw)
    if protocol.get("schema_version") != 1 or protocol.get("kind") != "prospective_research_registration":
        raise HoldoutError("Unsupported holdout protocol")
    times = []
    for key in ("registered_at_utc", "start_utc", "end_exclusive_utc"):
        value = datetime.fromisoformat(protocol[key])
        _require_utc(value, key)
        times.append(value)
    if not times[0] < times[1] < times[2]:
        raise HoldoutError("Registration must precede the entire evaluation window")
    if not isinstance(protocol.get("frozen_files"), dict) or not protocol["frozen_files"]:
        raise HoldoutError("No frozen research artifacts")
    return protocol


def verify_frozen_files(protocol: dict, frozen_root: Path) -> None:
    root = frozen_root.resolve()
    for relative, expected in protocol["frozen_files"].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise HoldoutError("Frozen artifact missing or outside snapshot")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise HoldoutError(f"Frozen artifact fingerprint mismatch: {relative}")


def assert_no_sealed_overlap(registry: Path, *, now: datetime, start: datetime, end: datetime) -> None:
    """Block implicit interim replays that intersect any registered sealed window."""
    for name, value in (("now", now), ("start", start), ("end", end)):
        _require_utc(value, name)
    if not registry.exists():
        return
    data = json.loads(registry.read_text())
    if data.get("schema_version") != 1 or not isinstance(data.get("registrations"), list):
        raise HoldoutError("Unsupported prospective registry")
    root = registry.resolve().parents[1]
    for entry in data["registrations"]:
        path = (root / entry["protocol"]).resolve()
        if not path.is_relative_to(root):
            raise HoldoutError("Protocol reference escapes repository")
        protocol = read_protocol(path, entry["sha256"])
        first = datetime.fromisoformat(protocol["start_utc"])
        last = datetime.fromisoformat(protocol["end_exclusive_utc"])
        if now < last and start < last and end > first:
            raise HoldoutError("Requested replay overlaps a sealed registered holdout")


def assert_holdout_released(
    protocol: dict, *, now: datetime, start: datetime, end: datetime, frozen_root: Path,
    replay_path: Path,
) -> None:
    """Call before opening quote inputs; time release alone grants no gate acceptance."""
    for name, value in (("now", now), ("start", start), ("end", end)):
        _require_utc(value, name)
    expected_start = datetime.fromisoformat(protocol["start_utc"])
    expected_end = datetime.fromisoformat(protocol["end_exclusive_utc"])
    if start != expected_start or end != expected_end:
        raise HoldoutError("Requested interval differs from the registered holdout")
    if now < expected_end:
        raise HoldoutError("Holdout evaluation remains sealed until its full end boundary")
    verify_frozen_files(protocol, frozen_root)
    expected = protocol["frozen_files"].get("scripts/replay_m15_reversal.py")
    if expected is None or hashlib.sha256(replay_path.read_bytes()).hexdigest() != expected:
        raise HoldoutError("Replay implementation differs from the registered snapshot")

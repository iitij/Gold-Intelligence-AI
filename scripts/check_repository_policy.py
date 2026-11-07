"""Bootstrap policy with explicit exceptions, valid even under python -O.

This is not a security certification. It prevents accidental weakening of
research-only defaults, unsafe source imports and direct broker execution.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from check_core_safety import CoreSafetyViolation, check_env_defaults, scan_core

ROOT = Path(__file__).resolve().parents[1]


def check_policy(root: Path = ROOT) -> None:
    try:
        check_env_defaults((root / ".env.example").read_text(encoding="utf-8"))
    except OSError as exc:
        raise CoreSafetyViolation("Missing .env.example") from exc
    if (root / ".env").exists():
        raise CoreSafetyViolation("Sensitive .env file in repository directory")
    registry = root / "sources/sources.lock.json"
    entries = json.loads(registry.read_text(encoding="utf-8"))["sources"]
    if not entries:
        raise CoreSafetyViolation("Missing source provenance list")
    for item in entries:
        if not re.fullmatch(r"[0-9a-f]{40}", str(item.get("commit", ""))):
            raise CoreSafetyViolation("Unpinned source SHA")
        if item.get("mode", "").startswith("snapshot") and item.get(
            "license_status"
        ) not in {"MIT", "Apache-2.0"}:
            raise CoreSafetyViolation("Unreviewed source license")
    scan_core(root / "src/goldintel")


def main() -> None:
    check_policy()
    print("PASS: fail-closed first-party research policy; security audit still required")


if __name__ == "__main__":
    main()

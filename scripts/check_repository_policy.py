"""Bootstrap guardrails; not a complete security audit."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    cfg = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert all(x in cfg for x in (
        "GOLD_ALLOW_LIVE=false",
        "GOLD_EXECUTION_ENABLED=false",
        "GOLD_TRADING_MODE=paper",
    ))
    assert not (ROOT / ".env").exists(), "Remove real .env before publishing"
    entries = json.loads((ROOT / "sources/sources.lock.json").read_text())["sources"]
    for entry in entries:
        assert len(entry["commit"]) == 40
        if entry["mode"].startswith("snapshot"):
            assert entry["license_status"] in {"MIT", "Apache-2.0"}
    print("PASS: bootstrap policy; security review still required")


if __name__ == "__main__":
    main()

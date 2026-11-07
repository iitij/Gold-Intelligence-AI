import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_locked_sources_exact_shas():
    data = json.loads((ROOT / "sources/sources.lock.json").read_text())
    assert data["format_version"] == 1
    for source in data["sources"]:
        assert len(source["commit"]) == 40
        assert all(c in "0123456789abcdef" for c in source["commit"])
        assert source["url"].startswith("https://github.com/")


def test_no_agpl_or_unknown_license_snapshots():
    data = json.loads((ROOT / "sources/sources.lock.json").read_text())
    for source in data["sources"]:
        license_status = source["license_status"].lower()
        if "agpl" in license_status or "unknown" in license_status or "not-located" in license_status:
            assert source["mode"] == "reference-only"


def test_weight_artifacts_are_not_falsely_marked_ready():
    data = json.loads((ROOT / "models/model_catalog.json").read_text())
    assert all(m.get("status") not in ("production", "deployed") for m in data["candidates"])

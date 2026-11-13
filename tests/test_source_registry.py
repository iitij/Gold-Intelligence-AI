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


def test_source_provenance_is_unambiguous():
    sources = json.loads((ROOT / "sources/sources.lock.json").read_text())["sources"]
    assert len({source["repository"] for source in sources}) == len(sources)
    assert all(source["name"] and source["mode"] and source["role"] for source in sources)


def test_weight_artifacts_are_not_falsely_marked_ready():
    data = json.loads((ROOT / "models/model_catalog.json").read_text())
    assert all(m.get("status") not in ("production", "deployed") for m in data["candidates"])

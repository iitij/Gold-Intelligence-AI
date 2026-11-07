"""Registry and archive policy tests. Untrusted third-party files are never imported."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_new_candidates_all_have_sha_and_license_status():
    data = json.loads(
        (ROOT / "sources/research_candidates_2026_11_08.lock.json").read_text()
    )
    records = data["candidates"]
    assert len(records) == 10
    assert len({c["id"] for c in records}) == len(records)
    assert len({c["repository"] for c in records}) == len(records)
    for c in records:
        assert re.fullmatch(r"[a-f0-9]{40}", c["commit"])
        assert c["license"]
        assert c["issues"]
        assert c["reviewed_on"] == "2026-11-08"


def test_no_unreviewed_source_is_authorized_for_copy_or_runtime():
    records = json.loads(
        (ROOT / "sources/research_candidates_2026_11_08.lock.json").read_text()
    )["candidates"]
    scoped = {x["repository"] for x in records if x["decision"] == "one-time-offline-review"}
    assert scoped == {
        "BorjaGomezSolorzano/Metatrader-Bridge", "OutOfSampleLab/oos-lab"
    }
    for candidate in records:
        if candidate["license"] not in {"MIT", "BSD-3-Clause"}:
            assert candidate["decision"] != "one-time-offline-review"
        assert candidate["decision"] != "runtime-approved"


def test_immutable_reference_archive_is_optional_until_review_merge():
    from importlib.util import module_from_spec, spec_from_file_location

    path = ROOT / "scripts/verify_research_refs.py"
    spec = spec_from_file_location("gold_ref_integrity", path)
    module = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    assert module.verify_archive(ROOT) >= 0

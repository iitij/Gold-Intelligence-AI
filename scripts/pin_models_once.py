"""One-time pin of vetted Hugging Face model repositories. No weight download."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "models/foundation_candidates.json"
LOCK = ROOT / "models/foundation_weights.lock.json"
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def fetch_model_info(repo_id: str) -> dict:
    url = "https://huggingface.co/api/models/" + urllib.parse.quote(repo_id, safe="/")
    request = urllib.request.Request(url, headers={"User-Agent": "gold-intelligence-ai/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def pin_all(candidates: dict, fetch=fetch_model_info) -> dict:
    assets = []
    for entry in candidates["candidates"]:
        model = fetch(entry["repo_id"])
        revision = model.get("sha", "")
        if not SHA40.fullmatch(revision):
            raise ValueError("Model revision is missing a complete commit SHA")
        if model.get("id") != entry["repo_id"]:
            raise ValueError("Model repository identity mismatch")
        license_label = (model.get("cardData") or {}).get("license") or model.get("license")
        if license_label is not None and license_label.lower() != entry["license_expected"]:
            raise ValueError("Model license differs from reviewed candidate")
        siblings = model.get("siblings") or []
        weights = sorted(
            item["rfilename"] for item in siblings
            if item.get("rfilename", "").endswith(".safetensors")
        )
        if not weights:
            raise ValueError("No safetensors checkpoint for " + entry["id"])
        assets.append(
            {
                "id": entry["id"],
                "repo_id": entry["repo_id"],
                "revision": revision,
                "license_expected": entry["license_expected"],
                "license_verified_via_api": bool(license_label),
                "files_expected_safetensors": weights,
                "downloaded": False,
                "approved_for_trading": False,
            }
        )
    return {
        "schema_version": 1,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "policy": "immutable-no-upstream-refresh; metadata-only; no weights included",
        "assets": assets,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if LOCK.exists():
        raise SystemExit("Immutable lock exists; no overwrite or upstream refresh permitted")
    if not args.confirm:
        print("NO CHANGE: pass --confirm to resolve revisions once (network required)")
        return
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    lock = pin_all(candidates)
    tmp = LOCK.with_suffix(".lock.tmp")
    tmp.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(LOCK)
    print("Pinned", len(lock["assets"]), "foundation models. No weights downloaded.")


if __name__ == "__main__":
    main()

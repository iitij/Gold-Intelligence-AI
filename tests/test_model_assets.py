"""Model asset operations must remain explicit and offline-safe."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_all_models_registered():
    catalog = json.loads((ROOT / "models/foundation_candidates.json").read_text())
    ids = [entry["id"] for entry in catalog["candidates"]]
    assert len(ids) == len(set(ids))
    assert {"qwen3-4b", "qwen35-2b", "chronos-2"} == set(ids)
    assert {x["id"] for x in catalog["train_from_scratch"]} >= {
        "lightgbm-xauusd", "catboost-xauusd", "nhits-xauusd"
    }
    assert all(x["status"] == "candidate-not-downloaded" for x in catalog["candidates"])


def test_list_does_not_require_weight_download():
    result = subprocess.run(
        [sys.executable, "scripts/model_assets.py", "list"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    assert "Qwen/Qwen3-4B" in result.stdout
    assert "LightGBM" in result.stdout


def test_download_requires_explicit_confirmation():
    result = subprocess.run(
        [sys.executable, "scripts/model_assets.py", "download", "--model", "qwen3-4b"],
        cwd=ROOT, check=False, capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "--confirm is required" in result.stderr


def test_pinning_requires_explicit_confirmation():
    result = subprocess.run(
        [sys.executable, "scripts/pin_models_once.py"],
        cwd=ROOT, check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0 or "Immutable lock exists" in result.stderr
    if result.returncode == 0:
        assert "NO CHANGE" in result.stdout

"""Persisted research samples must preserve provenance and purged label boundaries."""
import importlib.util
import json
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("lightgbm")
pytest.importorskip("catboost")
pytest.importorskip("sklearn")


@pytest.fixture
def package(tmp_path, monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("training_set", scripts / "prepare_historical_training_set.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    time = pd.date_range("2025-01-01", periods=1500, freq="15min")
    price = pd.Series(range(len(time)), dtype=float) / 100 + 2000
    bars = pd.DataFrame({
        "broker_symbol": "XAUUSD", "timeframe": "M15",
        "server_time": time.strftime("%Y.%m.%d %H:%M:%S"),
        "open": price, "high": price + 2, "low": price - 2, "close": price + .5,
        "tick_volume": 100, "spread_points": 15, "real_volume": 0,
    })
    source = tmp_path / "original.csv"
    bars.to_csv(source, index=False)
    output = tmp_path / "package"
    manifest = module.prepare_package([source], output, "2025-01-05", "2025-01-10")
    return module, source, output, manifest


def rewrite_manifest(output, manifest):
    (output / "manifest.json").write_text(json.dumps(manifest))


def test_round_trip_reproducible_and_provenance_preserved(package, tmp_path):
    module, source, output, manifest = package
    total = module.verify_package(output)
    assert total == sum(info["rows"] for record in manifest["feeds"][source.name]["horizons"].values()
                        for info in record["splits"].values())
    repeated = module.prepare_package([source], tmp_path / "second", "2025-01-05", "2025-01-10")
    assert repeated == manifest
    assert not manifest["final_holdout_locked"]
    assert not manifest["approved_for_training_or_trading"]
    for horizon, record in manifest["feeds"][source.name]["horizons"].items():
        # Exactly h decisions before each boundary have outcomes at/after it.
        assert record["exclusions"]["purged_boundary_samples"] == 2 * int(horizon)
        for info in record["splits"].values():
            x = pd.read_csv(output / info["features"])
            assert list(x.columns) == ["sample_id", "decision_native", *module.FEATURE_COLUMNS]
            assert "up_label" not in x and "forward_return" not in x and "source_row" not in x
    with pytest.raises(FileExistsError):
        module.prepare_package([source], output, "2025-01-05", "2025-01-10")


def test_hash_and_source_mutation_are_rejected(package):
    module, source, output, manifest = package
    first = next(iter(manifest["files"]))
    (output / first).write_text((output / first).read_text() + "\n")
    with pytest.raises(ValueError, match="fingerprint"):
        module.verify_package(output)
    source.write_text(source.read_text() + "\n")
    with pytest.raises(ValueError, match="Source fingerprint"):
        module.verify_package(output)


def test_rehashed_cross_boundary_label_still_rejected(package):
    module, source, output, manifest = package
    info = manifest["feeds"][source.name]["horizons"]["1"]["splits"]["train"]
    x = pd.read_csv(output / info["features"], float_precision="round_trip")
    y = pd.read_csv(output / info["labels"], float_precision="round_trip")
    x.loc[x.index[-1], "decision_native"] = "2025-01-04 23:45:00"
    y.loc[y.index[-1], "outcome_native"] = "2025-01-05 00:00:00"
    for kind, frame in (("features", x), ("labels", y)):
        frame.to_csv(output / info[kind], index=False, float_format="%.17g")
        manifest["files"][info[kind]] = module.digest(output / info[kind])
    rewrite_manifest(output, manifest)
    with pytest.raises(ValueError, match="leaks across"):
        module.verify_package(output)


def test_rehashed_false_return_still_rejected_against_source(package):
    module, source, output, manifest = package
    info = manifest["feeds"][source.name]["horizons"]["1"]["splits"]["train"]
    path = output / info["labels"]
    y = pd.read_csv(path, float_precision="round_trip")
    y.loc[0, "forward_return"] += .01
    y.to_csv(path, index=False, float_format="%.17g")
    manifest["files"][info["labels"]] = module.digest(path)
    rewrite_manifest(output, manifest)
    with pytest.raises(ValueError, match="original source rows"):
        module.verify_package(output)

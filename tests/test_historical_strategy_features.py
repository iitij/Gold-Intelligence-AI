"""Causality regression for the historical strategy training features."""
import importlib.util
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("lightgbm")
pytest.importorskip("catboost")
pytest.importorskip("sklearn")


def test_future_price_changes_do_not_change_past_features(tmp_path, monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "historical_training", scripts / "train_historical_strategies.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    time = pd.date_range("2025-01-01", periods=1500, freq="15min")
    price = pd.Series(range(1500), dtype=float) / 100 + 2000
    frame = pd.DataFrame({
        "broker_symbol": "XAUUSD", "timeframe": "M15",
        "server_time": time.strftime("%Y.%m.%d %H:%M:%S"),
        "open": price, "high": price + 2, "low": price - 2,
        "close": price + .5, "tick_volume": 100,
        "spread_points": 15, "real_volume": 0,
    })
    original = tmp_path / "original.csv"
    modified = tmp_path / "modified.csv"
    frame.to_csv(original, index=False)
    cutoff = 1200
    frame.loc[cutoff:, ["open", "high", "low", "close"]] *= 1.1
    frame.to_csv(modified, index=False)
    before, _, _, _ = module.samples(original)
    after, _, _, _ = module.samples(modified)
    pd.testing.assert_frame_equal(before.loc[:cutoff - 2], after.loc[:cutoff - 2])
    as_of = time[1000] + pd.Timedelta(minutes=7)
    available, _, _, _ = module.samples(original, as_of=as_of)
    assert available.decision_server_time.max() <= as_of
    assert available.index[-1] == 999
    assert before.iloc[-1].notna().all()
    assert before.decision_server_time.iloc[-1] == time[-1] + pd.Timedelta(minutes=15)
    from research_m15_direction import prepare
    historical, _ = prepare(original)
    columns = ["return_1", "return_4", "range", "body", "tick_volume"]
    pd.testing.assert_frame_equal(
        before.loc[historical.index, columns], historical[columns]
    )

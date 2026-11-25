"""Independent reconciliation of historical strategy replay output."""
import importlib.util
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("lightgbm")
pytest.importorskip("catboost")


@pytest.mark.parametrize("strategy", ["rejection", "breakout"])
def test_ledger_reconciles_returns_and_has_no_overlap(tmp_path, monkeypatch, strategy):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("strategy_replay", scripts / "evaluate_session_rejection.py")
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)
    import numpy as np

    time = pd.date_range("2025-12-25", periods=1200, freq="15min")
    rng = np.random.default_rng(42)
    price = 2000 + np.cumsum(rng.normal(0, 2, len(time)))
    bars = pd.DataFrame({
        "broker_symbol": "XAUUSD", "timeframe": "M15",
        "server_time": time.strftime("%Y.%m.%d %H:%M:%S"),
        "open": price, "high": price + 3, "low": price - 3,
        "close": price + .5, "tick_volume": 100,
        "spread_points": 15, "real_volume": 0,
    })
    path = tmp_path / "bars.csv"
    bars.to_csv(path, index=False)
    report = replay.evaluate(path, strategy)
    total = 0
    for horizon in report["horizons"].values():
        for result in horizon.values():
            ledger = result["trade_ledger"]
            assert len(ledger) == result["sequential_trades"]
            for left, right in zip(ledger, ledger[1:]):
                assert pd.Timestamp(left["exit_time"]) <= pd.Timestamp(right["entry_time"])
            if ledger:
                returns = [t["direction"] * (t["exit_bid_close"] / t["entry_bid_open"] - 1) for t in ledger]
                assert np.mean(returns) * 10000 == pytest.approx(result["sequential_gross_mean_bps"])
                assert np.prod(1 + np.array(returns)) - 1 == pytest.approx(result["sequential_compounded_return"])
            total += len(ledger)
    assert total > 0

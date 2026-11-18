"""Read XAUUSD Bid/Ask and recent raw M15/H1/H4 rows from Headway-Demo."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

COUNTS = {"M15": 40, "H1": 4, "H4": 3}
MODEL_HISTORY_COUNT = 300
OHLC = ("open", "high", "low", "close")


def read_rates(mt5, timeframe, count, name):
    before = datetime.now(timezone.utc)
    rates = mt5.copy_rates_from_pos("XAUUSD", timeframe, 0, count)
    after = datetime.now(timezone.utc)
    if rates is None or mt5.last_error()[0] != 1 or not 0 < len(rates) <= count:
        raise RuntimeError(f"Failed to read {name} rates")
    return {
        "host_utc_before": before.isoformat(), "host_utc_after": after.isoformat(),
        "bars": [{"native_open_seconds": int(row["time"]),
                  **{key: str(float(row[key])) for key in OHLC},
                  **{key: int(row[key]) for key in ("tick_volume", "real_volume", "spread")}}
                 for row in rates],
    }


def capture(mt5, *, model_context=False):
    account = mt5.account_info()
    terminal = mt5.terminal_info()
    if account is None or account.server != "Headway-Demo" or terminal is None or not terminal.connected:
        raise RuntimeError("Connected Headway-Demo session required")
    history = read_rates(mt5, mt5.TIMEFRAME_M15, MODEL_HISTORY_COUNT, "model context") if model_context else None
    frames = {name: read_rates(mt5, timeframe, COUNTS[name], name) for name, timeframe in (
        ("M15", mt5.TIMEFRAME_M15), ("H1", mt5.TIMEFRAME_H1), ("H4", mt5.TIMEFRAME_H4),
    )}
    before = datetime.now(timezone.utc)
    tick = mt5.symbol_info_tick("XAUUSD")
    after = datetime.now(timezone.utc)
    current = mt5.account_info()
    terminal = mt5.terminal_info()
    if (tick is None or current is None or current.server != account.server
            or current.login != account.login or terminal is None or not terminal.connected):
        raise RuntimeError("Quote unavailable or Headway-Demo session changed during capture")
    return {
        "schema_version": 1, "kind": "observed_headway_market_inputs",
        "server": "Headway-Demo", "symbol": "XAUUSD", "frames": frames,
        **({"model_history": history} if history is not None else {}),
        "quote": {"host_utc_before": before.isoformat(), "host_utc_after": after.isoformat(),
                  "native_tick_msc": int(tick.time_msc), "bid": str(tick.bid), "ask": str(tick.ask)},
        "collector_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--terminal", required=True)
    parser.add_argument("--portable", action="store_true")
    parser.add_argument("--model-context", action="store_true", help="Also read the last 300 M15 rows")
    args = parser.parse_args()
    import MetaTrader5 as mt5

    if not mt5.initialize(args.terminal, portable=args.portable, timeout=15000):
        raise SystemExit(f"MT5 initialization error {mt5.last_error()[0]}")
    try:
        data = capture(mt5, model_context=args.model_context)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(data, indent=2, allow_nan=False) + "\n")
    finally:
        mt5.shutdown()
    print("Captured Headway-Demo market inputs")


if __name__ == "__main__":
    main()

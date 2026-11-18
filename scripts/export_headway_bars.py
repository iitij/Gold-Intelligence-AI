"""Export completed Headway-Demo M15 bars in native chronology."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--terminal", required=True)
    parser.add_argument("--start", required=True, type=datetime.fromisoformat)
    parser.add_argument("--offset-seconds", required=True, type=int)
    parser.add_argument("--portable", action="store_true")
    args = parser.parse_args()
    import MetaTrader5 as mt5

    if args.start.utcoffset() != timedelta(0):
        parser.error("--start must be UTC encoded native chronology")
    if not mt5.initialize(args.terminal, portable=args.portable, timeout=15000):
        raise SystemExit(f"MT5 initialization error {mt5.last_error()[0]}")
    try:
        account = mt5.account_info()
        if account is None or account.server != "Headway-Demo":
            raise SystemExit("Expected Headway-Demo")
        native_now = datetime.now(timezone.utc) + timedelta(seconds=args.offset_seconds)
        rates = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_M15, args.start, native_now)
        if rates is None or mt5.last_error()[0] != 1:
            raise SystemExit("MT5 bar history query failed")
        completed = [r for r in rates if int(r["time"]) + 900 <= native_now.timestamp()]
        if not completed:
            raise SystemExit("No completed M15 bars")
        with args.output.open("x", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["broker_symbol", "timeframe", "server_time", "open", "high",
                             "low", "close", "tick_volume", "spread_points", "real_volume"])
            for rate in completed:
                writer.writerow([
                    "XAUUSD", "M15",
                    datetime.fromtimestamp(int(rate["time"]), timezone.utc).strftime("%Y.%m.%d %H:%M:%S"),
                    *[float(rate[k]) for k in ("open", "high", "low", "close")],
                    int(rate["tick_volume"]), int(rate["spread"]), int(rate["real_volume"]),
                ])
        print(f"Exported {len(completed)} completed native-time M15 bars")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()

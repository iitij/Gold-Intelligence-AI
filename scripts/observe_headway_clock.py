"""Record host UTC and changed Headway-Demo quote timestamps."""

import argparse
import json
import time
from datetime import datetime, timezone


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terminal")
    parser.add_argument("--portable", action="store_true")
    parser.add_argument("--seconds", type=int, default=60)
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    terminal = (args.terminal,) if args.terminal else ()

    import MetaTrader5 as mt5

    if not mt5.initialize(*terminal, portable=args.portable, timeout=10000):
        raise SystemExit(f"MT5 initialization error {mt5.last_error()[0]}")
    try:
        account = mt5.account_info()
        if account is None or account.server != "Headway-Demo":
            raise SystemExit("Expected Headway-Demo")
        previous = None
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            before = datetime.now(timezone.utc)
            tick = mt5.symbol_info_tick("XAUUSD")
            after = datetime.now(timezone.utc)
            if tick is not None and tick.time_msc != previous:
                native = datetime.fromtimestamp(tick.time_msc / 1000, timezone.utc)
                print(json.dumps({
                    "kind": "initial_cached_quote" if previous is None else "changed_quote",
                    "host_utc_before": before.isoformat(),
                    "host_utc_after": after.isoformat(),
                    "native_tick_ms": tick.time_msc,
                    "native_minus_host_seconds": (native - after).total_seconds(),
                }), flush=True)
                previous = tick.time_msc
            time.sleep(0.1)
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()

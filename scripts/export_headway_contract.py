"""Read selected Headway-Demo XAUUSD contract fields and aggregate deal fees."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--terminal", required=True)
    parser.add_argument("--history-start", type=datetime.fromisoformat)
    parser.add_argument("--portable", action="store_true")
    args = parser.parse_args()
    if args.history_start is not None and args.history_start.utcoffset() != timedelta(0):
        parser.error("--history-start must be explicitly UTC")
    import MetaTrader5 as mt5

    if not mt5.initialize(args.terminal, portable=args.portable, timeout=15000):
        raise SystemExit(f"MT5 initialization error {mt5.last_error()[0]}")
    try:
        account = mt5.account_info()
        if account is None or account.server != "Headway-Demo":
            raise SystemExit("Expected Headway-Demo")
        symbol = mt5.symbol_info("XAUUSD")
        if symbol is None:
            raise SystemExit("XAUUSD metadata unavailable")
        fields = (
            "point", "digits", "trade_contract_size", "trade_tick_size",
            "trade_tick_value_profit", "trade_tick_value_loss", "trade_calc_mode",
            "volume_min", "volume_max", "volume_step", "currency_base",
            "currency_profit", "currency_margin", "swap_mode", "swap_long",
            "swap_short", "swap_rollover3days", "trade_stops_level", "trade_freeze_level",
        )
        now = datetime.now(timezone.utc)
        # This is a history query range, not proof of deal timestamp UTC mapping.
        start = args.history_start or now.replace(hour=0, minute=0, second=0, microsecond=0)
        deals = mt5.history_deals_get(start, now)
        status = mt5.last_error()[0]
        matches = [deal for deal in deals if deal.symbol == "XAUUSD"] if deals is not None else []
        report = {
            "observed_at_utc": now.isoformat(), "server": account.server,
            "account_currency": account.currency, "pricing_tier": None,
            "symbol": "XAUUSD", "contract": {key: getattr(symbol, key) for key in fields},
            "fee_query": {
                "start": start.isoformat(), "end": now.isoformat(),
                "status_code": status, "matching_deals": len(matches),
                "commission_sum": sum(d.commission for d in matches) if matches else None,
                "fee_sum": sum(d.fee for d in matches) if matches else None,
                "swap_sum": sum(d.swap for d in matches) if matches else None,
            },
            "limitations": ["Pricing tier requires separate confirmation",
                            "Current contract does not establish historical specifications",
                            "Aggregate fees do not establish a per-volume cost schedule"],
        }
        with args.output.open("x") as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()

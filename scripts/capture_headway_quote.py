"""Capture one current Headway-Demo Bid/Ask observation; never sends broker orders."""
import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--clock-evidence", type=Path, required=True)
    parser.add_argument("--terminal", required=True)
    parser.add_argument("--portable", action="store_true")
    args = parser.parse_args()
    evidence = json.loads(args.clock_evidence.read_text())
    now = datetime.now(timezone.utc)
    if (evidence["broker_server"] != "Headway-Demo"
            or evidence["observed_date"] != str(now.date())
            or evidence["matched_changed_quote_timestamps"] < 1):
        parser.error("Clock evidence must match today's observed Headway-Demo session")
    import MetaTrader5 as mt5

    if not mt5.initialize(args.terminal, portable=args.portable, timeout=15000):
        raise SystemExit(f"MT5 initialization error {mt5.last_error()[0]}")
    try:
        account = mt5.account_info()
        terminal = mt5.terminal_info()
        if account is None or account.server != "Headway-Demo" or terminal is None or not terminal.connected:
            raise SystemExit("Connected Headway-Demo session required")
        before = datetime.now(timezone.utc)
        quote = mt5.symbol_info_tick("XAUUSD")
        after = datetime.now(timezone.utc)
        if quote is None:
            raise SystemExit("No XAUUSD quote")
        bid, ask = Decimal(str(quote.bid)), Decimal(str(quote.ask))
        if not all(value.is_finite() and value > 0 for value in (bid, ask)) or ask < bid:
            raise SystemExit("Invalid observed Bid/Ask")
        midpoint = before + (after - before) / 2
        native_minus_host = quote.time_msc / 1000 - midpoint.timestamp()
        residual = native_minus_host - evidence["native_minus_utc_seconds"]
        report = {
            "schema_version": 1, "kind": "observed_headway_quote",
            "server": "Headway-Demo", "symbol": "XAUUSD",
            "host_utc_before": before.isoformat(), "host_utc_after": after.isoformat(),
            "observed_at_utc": after.isoformat(), "bid": str(bid), "ask": str(ask),
            "native_tick_msc": int(quote.time_msc), "native_minus_host_seconds": native_minus_host,
            "residual_after_session_offset_seconds": residual,
            "source_verified": bool(abs(residual) <= 2 and after - before <= timedelta(seconds=1)),
            "clock_evidence_sha256": hashlib.sha256(args.clock_evidence.read_bytes()).hexdigest(),
            "collector_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "utc_semantics": "Actual host retrieval completion; native event timestamp retained separately",
            "execution_ready": False,
        }
        with args.output.open("x") as stream:
            stream.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
        print("Captured one current Bid/Ask observation")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()

"""Read aggregate cost distributions from existing Headway-Demo deal history."""
import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


def summarize_deal_costs(deals, status, symbol):
    if deals is None or status != 1:
        return {"status": "query_failed", "symbol_groups": None, "unattributed_deal_type_counts": None}
    groups = defaultdict(list)
    unattributed = Counter()
    for deal in deals:
        if deal.symbol == symbol:
            groups[deal.type, deal.entry].append(deal)
        elif not deal.symbol:
            # Standalone charges may not carry a symbol or a nonzero commission field.
            unattributed[deal.type] += 1
    summaries = []
    for (deal_type, entry), rows in sorted(groups.items()):
        volumes = [Decimal(str(deal.volume)) for deal in rows]
        summary = {"deal_type": deal_type, "deal_entry": entry, "count": len(rows),
                   "volume_lots_min": str(min(volumes)), "volume_lots_max": str(max(volumes))}
        for field in ("commission", "fee", "swap"):
            values = [Decimal(str(getattr(deal, field))) for deal in rows]
            if any(not v.is_finite() for v in values):
                raise ValueError(f"Nonfinite {field} in deal history")
            summary[field] = {"negative": sum(v < 0 for v in values), "zero": sum(v == 0 for v in values),
                              "positive": sum(v > 0 for v in values),
                              "min": str(min(values)), "max": str(max(values))}
        summaries.append(summary)
    return {"status": "observed_sample" if summaries else "no_symbol_deals",
            "symbol_groups": summaries,
            "unattributed_deal_type_counts": dict(sorted(unattributed.items())),
            "historical_cost_schedule_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--terminal", required=True)
    parser.add_argument("--history-start", required=True, type=datetime.fromisoformat)
    parser.add_argument("--portable", action="store_true")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if args.history_start.utcoffset() != timedelta(0) or args.history_start >= now:
        parser.error("--history-start must be explicitly UTC and before now")

    import MetaTrader5 as mt5

    if not mt5.initialize(args.terminal, portable=args.portable, timeout=15000):
        raise SystemExit(f"MT5 initialization error {mt5.last_error()[0]}")
    try:
        account = mt5.account_info()
        if account is None or account.server != "Headway-Demo":
            raise SystemExit("Expected Headway-Demo")
        deals = mt5.history_deals_get(args.history_start, now)
        status = mt5.last_error()[0]
        report = {"schema_version": 1, "server": account.server, "symbol": "XAUUSD",
                  "account_currency": account.currency, "query_start_argument": args.history_start.isoformat(),
                  "query_end_argument": now.isoformat(), "query_status_code": status,
                  "deal_clock_utc_verified": False, "historical_cost_schedule_verified": False,
                  **summarize_deal_costs(deals, status, "XAUUSD")}
        with args.output.open("x") as stream:
            stream.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
        if report["status"] != "observed_sample":
            raise SystemExit(2)
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()

"""Diagnose XAUUSD snapshot arithmetic without assuming account currency or readiness."""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from goldintel.data.broker_specs import BrokerSpecError, parse_spec


def check_contract(path: Path, *, symbol: str) -> dict:
    report = parse_spec(path, expected_symbol=symbol)
    before = Path(path).read_bytes()
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        values = {row["field"]: row["value"] for row in csv.DictReader(stream)}
    if Path(path).read_bytes() != before or parse_spec(path, expected_symbol=symbol) != report:
        raise BrokerSpecError("source changed during diagnosis")
    # This amount is in PROFIT currency, whereas MT5 tick values can be in
    # ACCOUNT currency. A mismatch requires review, never automatic correction.
    theoretical = Decimal(values["contract_size"]) * Decimal(values["tick_size"])
    ratios = {side: str(Decimal(values[f"tick_value_{side}"]) / theoretical)
              for side in ("profit", "loss")}
    return {
        "snapshot_validation": asdict(report),
        "linear_contract_tick_amount_in_profit_currency": str(theoretical),
        "reported_tick_value_to_linear_amount_ratios": ratios,
        "same_currency_assumption_verified": False,
        "calculation_mode": values["trade_calc_mode"],
        "requires_tick_value_review": any(Decimal(v) != 1 for v in ratios.values()),
        "interpretation": "Diagnostic only: verify account currency, conversion, calculation mode and broker specification before interpreting ratios.",
        "historical_timezone_verified": False,
        "training_ready": False,
        "execution_ready": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--symbol", required=True)
    args = parser.parse_args()
    try:
        result = check_contract(args.snapshot, symbol=args.symbol)
    except (BrokerSpecError, OSError) as exc:
        parser.exit(2, f"INVALID SNAPSHOT: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

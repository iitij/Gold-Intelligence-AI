"""Validate read-only MT5 XAUUSD contract snapshot without inferring training readiness.

MQL5 symbol properties are observed at ONE time only; historical values, DST,
execution loss values, margin, and FX conversion remain unverified.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

REQUIRED = {
    "schema_version", "asset_id", "broker_symbol", "snapshot_server_time",
    "snapshot_local_estimated_utc", "observed_server_offset_seconds",
    "point", "digits", "tick_size", "tick_value_profit", "tick_value_loss",
    "contract_size", "volume_min", "volume_max", "volume_step",
    "stops_level_points", "freeze_level_points", "currency_profit",
    "trade_calc_mode", "trade_mode", "trade_execution_mode",
    "historical_dst_verified", "contains_account_identifiers",
}
POSITIVE = {"point", "tick_size", "tick_value_profit", "tick_value_loss",
            "contract_size", "volume_min", "volume_max", "volume_step"}
NONNEGATIVE_INTEGERS = {"digits", "stops_level_points", "freeze_level_points",
                        "trade_calc_mode", "trade_mode", "trade_execution_mode"}


class BrokerSpecError(ValueError):
    """Contract snapshot is incomplete or cannot be trusted for research."""


@dataclass(frozen=True)
class BrokerSpecReport:
    schema_version: int
    raw_sha256: str
    broker_symbol: str
    currency_profit: str
    server_time_unverified: str
    observed_offset_seconds_unverified: int
    tick_size: str
    tick_value_loss: str
    volume_min: str
    volume_step: str
    volume_max: str
    historic_contract_validity_verified: bool = False
    timezone_dst_verified: bool = False
    loss_value_account_currency_verified: bool = False
    training_ready: bool = False
    execution_ready: bool = False


def _decimal(value: str, field: str) -> Decimal:
    try:
        n = Decimal(value)
    except InvalidOperation as exc:
        raise BrokerSpecError(f"Bad numeric {field}") from exc
    if not n.is_finite():
        raise BrokerSpecError(f"Non-finite {field}")
    return n


def parse_spec(path: Path, *, expected_symbol: str) -> BrokerSpecReport:
    if not expected_symbol.upper().startswith("XAUUSD"):
        raise BrokerSpecError("Only explicit XAUUSD broker symbols supported")
    path = Path(path)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["field", "value"]:
            raise BrokerSpecError("Expected field,value CSV header")
        rows = list(reader)
    if any(None in row or row.get("field") is None or row.get("value") is None
           for row in rows):
        raise BrokerSpecError("Invalid CSV row")
    data = {row["field"]: row["value"] for row in rows}
    if len(data) != len(rows) or set(data) != REQUIRED:
        raise BrokerSpecError("Missing/duplicated/unrecognized specification fields")
    if (data["schema_version"] != "1" or data["asset_id"] != "XAUUSD" or
            data["broker_symbol"] != expected_symbol):
        raise BrokerSpecError("Unknown asset/symbol/schema")
    if (data["historical_dst_verified"] != "false" or
            data["contains_account_identifiers"] != "false"):
        raise BrokerSpecError("Unexpected source safety contract")
    for field in POSITIVE:
        if _decimal(data[field], field) <= 0:
            raise BrokerSpecError(f"Nonpositive {field}")
    for field in NONNEGATIVE_INTEGERS:
        n = _decimal(data[field], field)
        if n < 0 or n != n.to_integral_value():
            raise BrokerSpecError(f"Invalid integer {field}")
    if _decimal(data["volume_min"], "volume_min") > _decimal(
            data["volume_max"], "volume_max"):
        raise BrokerSpecError("Volume min exceeds max")
    if _decimal(data["tick_size"], "tick_size") < _decimal(data["point"], "point"):
        raise BrokerSpecError("Tick size smaller than point")
    try:
        server = datetime.strptime(data["snapshot_server_time"], "%Y.%m.%d %H:%M:%S")
        _ = datetime.strptime(data["snapshot_local_estimated_utc"], "%Y.%m.%d %H:%M:%S")
        seconds = int(data["observed_server_offset_seconds"])
    except ValueError as exc:
        raise BrokerSpecError("Invalid observed clocks/offset") from exc
    if abs(seconds) > 24 * 3600:
        raise BrokerSpecError("Implausible server-local UTC offset")
    currency = data["currency_profit"]
    if len(currency) != 3 or not currency.isalpha() or not currency.isupper():
        raise BrokerSpecError("Unrecognized profit currency")
    return BrokerSpecReport(
        schema_version=1,
        raw_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        broker_symbol=expected_symbol,
        currency_profit=currency,
        server_time_unverified=server.isoformat(),
        observed_offset_seconds_unverified=seconds,
        tick_size=data["tick_size"],
        tick_value_loss=data["tick_value_loss"],
        volume_min=data["volume_min"],
        volume_step=data["volume_step"],
        volume_max=data["volume_max"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--broker-symbol", required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = parse_spec(args.csv, expected_symbol=args.broker_symbol)
    except (BrokerSpecError, OSError) as exc:
        parser.exit(2, f"INVALID BROKER SPEC: {exc}\n")
    value = json.dumps(asdict(report), indent=2, ensure_ascii=False) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(value, encoding="utf-8")
    print(value, end="")


if __name__ == "__main__":
    main()

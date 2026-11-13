"""Validate a read-only MetaTrader 5 XAUUSD M15 CSV export.

Broker-server timestamps deliberately remain naive: no inference of UTC/DST is
allowed here. Output is a quality report, NOT trading-ready or training-ready
market data. No execution API or network access is used.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

COLUMNS = (
    "broker_symbol", "timeframe", "server_time", "open", "high", "low", "close",
    "tick_volume", "spread_points", "real_volume",
)
TIME_FORMAT = "%Y.%m.%d %H:%M:%S"
BAR_INTERVAL_SECONDS = 15 * 60


class MarketDataError(ValueError):
    """An MT5 export is invalid or incompatible with this reader."""


@dataclass(frozen=True)
class ValidationReport:
    format_version: int
    source_sha256: str
    broker_symbol: str
    timeframe: str
    rows: int
    first_server_time: str
    last_server_time: str
    gap_count: int
    maximum_gap_minutes: int
    timestamp_policy: str
    utc_verified: bool
    training_ready: bool
    execution_ready: bool


def _decimal(value: str | None, column: str, row: int) -> Decimal:
    try:
        number = Decimal(value if value is not None else "")
    except InvalidOperation as exc:
        raise MarketDataError(f"row {row}: invalid {column}") from exc
    if not number.is_finite():
        raise MarketDataError(f"row {row}: non-finite {column}")
    return number


def _integer(value: str | None, column: str, row: int) -> int:
    number = _decimal(value, column, row)
    if number < 0 or number != number.to_integral_value():
        raise MarketDataError(f"row {row}: invalid nonnegative integer {column}")
    return int(number)


def validate_mt5_csv(path: Path, *, expected_symbol: str) -> ValidationReport:
    return load_validated_mt5_csv(path, expected_symbol=expected_symbol)[0]


def load_validated_mt5_csv(
    path: Path, *, expected_symbol: str,
) -> tuple[ValidationReport, list[dict[str, str]]]:
    """Validate and return records from the exact bytes identified by the hash.

    Fail closed on malformed bars; report nonfatal weekend/session gaps.

    expected_symbol is an explicit broker-side XAUUSD symbol, e.g. XAUUSDm.
    A broker alias not beginning with XAUUSD requires a reviewed mapping.
    """
    path = Path(path)
    if not path.is_file():
        raise MarketDataError(f"CSV file not found: {path}")
    if not expected_symbol.upper().startswith("XAUUSD"):
        raise MarketDataError("Only broker symbols mapped to XAUUSD are accepted")

    snapshot = path.read_bytes()
    records = []
    rows = 0
    gaps = 0
    max_gap = 0
    first = None
    previous = None
    with io.StringIO(snapshot.decode("utf-8-sig"), newline="") as stream:
        reader = csv.DictReader(stream, delimiter=",")
        if reader.fieldnames != list(COLUMNS):
            raise MarketDataError("Unexpected schema: expected " + ",".join(COLUMNS))
        for row_num, record in enumerate(reader, start=2):
            if None in record or any(value is None for value in record.values()):
                raise MarketDataError(f"row {row_num}: missing or excess fields")
            if record["broker_symbol"] != expected_symbol:
                raise MarketDataError(f"row {row_num}: broker symbol mismatch")
            if record["timeframe"] != "M15":
                raise MarketDataError(f"row {row_num}: only M15 closed bars supported")
            try:
                bar_time = datetime.strptime(record["server_time"], TIME_FORMAT)
            except ValueError as exc:
                raise MarketDataError(f"row {row_num}: invalid server timestamp") from exc
            if bar_time.minute % 15 or bar_time.second:
                raise MarketDataError(f"row {row_num}: unaligned M15 candle")
            if previous is not None:
                delta = int((bar_time - previous).total_seconds())
                if delta <= 0 or delta % BAR_INTERVAL_SECONDS:
                    raise MarketDataError(f"row {row_num}: duplicate/out-of-order/unaligned time")
                if delta > BAR_INTERVAL_SECONDS:
                    gaps += 1
                    max_gap = max(max_gap, delta // 60)
            prices = {k: _decimal(record[k], k, row_num) for k in
                      ("open", "high", "low", "close")}
            if any(v <= 0 for v in prices.values()):
                raise MarketDataError(f"row {row_num}: non-positive price")
            if (prices["high"] < max(prices.values()) or
                    prices["low"] > min(prices.values())):
                raise MarketDataError(f"row {row_num}: malformed OHLC")
            for field in ("tick_volume", "spread_points", "real_volume"):
                _integer(record[field], field, row_num)
            first = first or bar_time
            previous = bar_time
            records.append(record)
            rows += 1
    if rows == 0:
        raise MarketDataError("CSV contains no closed bars")
    return ValidationReport(
        format_version=1,
        source_sha256=hashlib.sha256(snapshot).hexdigest(),
        broker_symbol=expected_symbol,
        timeframe="M15",
        rows=rows,
        first_server_time=first.isoformat(),
        last_server_time=previous.isoformat(),
        gap_count=gaps,
        maximum_gap_minutes=max_gap,
        timestamp_policy="BROKER_SERVER_UNVERIFIED_NO_UTC_CONVERSION",
        utc_verified=False,
        training_ready=False,
        execution_ready=False,
    ), records


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect an XAUUSD MT5 M15 export, read-only")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--broker-symbol", default="XAUUSD")
    parser.add_argument("--report", type=Path, help="Create a new JSON report; never overwrite a file")
    args = parser.parse_args()
    try:
        report = validate_mt5_csv(args.csv, expected_symbol=args.broker_symbol)
        content = json.dumps(asdict(report), indent=2, ensure_ascii=False) + "\n"
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.open("x", encoding="utf-8") as stream:
                stream.write(content)
    except (MarketDataError, OSError, UnicodeError) as exc:
        parser.exit(2, f"INVALID MT5 DATA: {exc}\n")
    print(content, end="")


if __name__ == "__main__":
    main()

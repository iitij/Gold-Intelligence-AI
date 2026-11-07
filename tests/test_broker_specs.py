"""Synthetic broker specification intake tests; no MetaTrader connection."""
import csv
from pathlib import Path

import pytest

from goldintel.data.broker_specs import BrokerSpecError, parse_spec

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = {
    "schema_version": "1",
    "asset_id": "XAUUSD",
    "broker_symbol": "XAUUSDm",
    "snapshot_server_time": "2026.11.08 12:00:00",
    "snapshot_local_estimated_utc": "2026.11.08 09:00:00",
    "observed_server_offset_seconds": "10800",
    "point": "0.01", "digits": "2", "tick_size": "0.01",
    "tick_value_profit": "1.0", "tick_value_loss": "1.0",
    "contract_size": "100", "volume_min": "0.01",
    "volume_max": "100", "volume_step": "0.01",
    "stops_level_points": "0", "freeze_level_points": "0",
    "currency_profit": "USD", "trade_calc_mode": "4",
    "trade_mode": "4", "trade_execution_mode": "2",
    "historical_dst_verified": "false",
    "contains_account_identifiers": "false",
}


def save_spec(tmp_path: Path, values: dict) -> Path:
    dest = tmp_path / "source.csv"
    with dest.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(("field", "value"))
        writer.writerows(values.items())
    return dest


def test_valid_snapshot_must_remain_not_training_ready(tmp_path):
    result = parse_spec(save_spec(tmp_path, EXAMPLE), expected_symbol="XAUUSDm")
    assert not result.training_ready
    assert not result.execution_ready
    assert not result.timezone_dst_verified
    assert not result.historic_contract_validity_verified
    assert result.broker_symbol == "XAUUSDm"
    assert len(result.raw_sha256) == 64


@pytest.mark.parametrize(("field", "bad"), [
    ("tick_size", "-1"), ("volume_step", "0"), ("volume_max", "0"),
    ("tick_value_loss", "NaN"), ("contract_size", "Infinity"),
    ("digits", "2.5"), ("currency_profit", "BAD.CCY"),
    ("observed_server_offset_seconds", "90000"),
    ("historical_dst_verified", "true"),
])
def test_invalid_snapshot_rejected(tmp_path, field, bad):
    values = dict(EXAMPLE)
    values[field] = bad
    with pytest.raises(BrokerSpecError):
        parse_spec(save_spec(tmp_path, values), expected_symbol="XAUUSDm")


def test_missing_or_unrecognized_metadata_rejected(tmp_path):
    values = dict(EXAMPLE)
    del values["volume_step"]
    with pytest.raises(BrokerSpecError):
        parse_spec(save_spec(tmp_path, values), expected_symbol="XAUUSDm")


def test_broker_symbol_mapping_requires_explicit_match(tmp_path):
    with pytest.raises(BrokerSpecError):
        parse_spec(save_spec(tmp_path, EXAMPLE), expected_symbol="GOLD")
    with pytest.raises(BrokerSpecError):
        parse_spec(save_spec(tmp_path, EXAMPLE), expected_symbol="XAUUSD")


def test_no_account_or_trade_commands_in_mql5_source():
    code = (ROOT / "mt5/ExportXAUUSD_SymbolSpec.mq5").read_text(encoding="utf-8")
    for forbidden in ("OrderSend(", "MqlTradeRequest", "AccountInfoInteger(",
                      "AccountInfoDouble(", "AccountInfoString(",
                      "PositionSelect(", "HistoryDealGet"):
        assert forbidden not in code
    assert "FileOpen(" in code and "SymbolInfoDouble(" in code

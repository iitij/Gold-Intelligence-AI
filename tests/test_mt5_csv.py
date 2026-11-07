"""Synthetic XAUUSD candles only; no trading APIs or real market claims."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from goldintel.data.mt5_csv import COLUMNS, MarketDataError, validate_mt5_csv

GOOD = [
    ["XAUUSDm", "M15", "2026.01.05 09:00:00", "2000.00", "2001.40", "1999.20", "2000.40", "120", "15", "0"],
    ["XAUUSDm", "M15", "2026.01.05 09:15:00", "2000.40", "2002.00", "2000.10", "2001.70", "135", "17", "0"],
]


def write_csv(path: Path, rows: list[list[str]], *, header=COLUMNS) -> Path:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def test_good_bars_are_broker_server_only(tmp_path):
    report = validate_mt5_csv(write_csv(tmp_path / "gold.csv", GOOD), expected_symbol="XAUUSDm")
    assert report.rows == 2
    assert report.gap_count == 0
    assert len(report.source_sha256) == 64
    assert report.first_server_time == "2026-01-05T09:00:00"
    assert not report.utc_verified
    assert not report.training_ready
    assert not report.execution_ready


def test_gap_reported_but_not_filled(tmp_path):
    rows = [GOOD[0], [*GOOD[1]]]
    rows[1][2] = "2026.01.05 10:15:00"
    report = validate_mt5_csv(write_csv(tmp_path / "gap.csv", rows), expected_symbol="XAUUSDm")
    assert report.gap_count == 1
    assert report.maximum_gap_minutes == 75
    assert report.rows == 2


@pytest.mark.parametrize("column,value", [
    (3, "NaN"), (4, "Infinity"), (5, "0"), (4, "1998.00"),
    (5, "2003.00"), (7, "-1"), (8, "-1"), (9, "0.5"),
    (0, "EURUSD"), (1, "H1"), (2, "2026.01.05 09:12:00"),
    (2, "2030-01-01T09:15:00"),
])
def test_reject_corrupt_fields(tmp_path, column, value):
    rows = [[*GOOD[0]], [*GOOD[1]]]
    rows[1][column] = value
    with pytest.raises(MarketDataError):
        validate_mt5_csv(write_csv(tmp_path / "bad.csv", rows), expected_symbol="XAUUSDm")


@pytest.mark.parametrize("bad_time", [
    "2026.01.05 09:00:00",  # duplicate
    "2026.01.05 08:45:00",  # backwards
])
def test_reject_bad_order(tmp_path, bad_time):
    rows = [GOOD[0], [*GOOD[1]]]
    rows[1][2] = bad_time
    with pytest.raises(MarketDataError):
        validate_mt5_csv(write_csv(tmp_path / "order.csv", rows), expected_symbol="XAUUSDm")


def test_reject_wrong_schema(tmp_path):
    path = write_csv(tmp_path / "schema.csv", GOOD, header=COLUMNS[:-1])
    with pytest.raises(MarketDataError, match="schema"):
        validate_mt5_csv(path, expected_symbol="XAUUSDm")


def test_reject_empty_csv(tmp_path):
    with pytest.raises(MarketDataError, match="no closed bars"):
        validate_mt5_csv(write_csv(tmp_path / "empty.csv", []), expected_symbol="XAUUSDm")


def test_reject_wrong_expected_asset(tmp_path):
    with pytest.raises(MarketDataError, match="XAUUSD"):
        validate_mt5_csv(write_csv(tmp_path / "asset.csv", GOOD), expected_symbol="EURUSD")


def test_reject_short_row(tmp_path):
    with pytest.raises(MarketDataError, match="fields"):
        validate_mt5_csv(write_csv(tmp_path / "short.csv", [GOOD[0][:-1]]), expected_symbol="XAUUSDm")


def test_reject_extra_column(tmp_path):
    with pytest.raises(MarketDataError, match="fields"):
        validate_mt5_csv(write_csv(tmp_path / "extra.csv", [GOOD[0] + ["secret"]]), expected_symbol="XAUUSDm")


def test_accept_utf8_bom(tmp_path):
    path = write_csv(tmp_path / "bom.csv", GOOD)
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    assert validate_mt5_csv(path, expected_symbol="XAUUSDm").rows == 2

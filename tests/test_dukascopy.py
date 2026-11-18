"""Legacy daily reference decoding must preserve price order and reject bad records."""
import lzma
import struct
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from goldintel.data.dukascopy import read_bid_m15
from goldintel.data.mt5_csv import MarketDataError


def encoded(rows):
    return lzma.compress(b"".join(struct.pack(">IIIIIf", *row) for row in rows))


def test_day_relative_utc_and_oclh_price_order(tmp_path):
    path = tmp_path / "bid.bi5"
    rows = [(minute * 60, 4500000, 4501001 + minute, 4499000, 4502000, .1)
            for minute in range(15)]
    rows.append((900, 4500000, 4500000, 4500000, 4500000, 0))
    path.write_bytes(encoded(rows))
    bars, quality = read_bid_m15(path, date(2026, 3, 30))
    assert list(bars) == [datetime(2026, 3, 30, tzinfo=timezone.utc)]
    assert next(iter(bars.values())) == {
        "open": Decimal("4500"), "close": Decimal("4501.015"),
        "low": Decimal("4499"), "high": Decimal("4502"),
    }
    assert quality["zero_volume_minutes_excluded"] == 1
    assert not quality["training_ready"]


@pytest.mark.parametrize("rows", [
    [(0, 1000, 1000, 900, 1100, 1), (0, 1000, 1000, 900, 1100, 1)],
    [(1, 1000, 1000, 900, 1100, 1)],
    [(86400, 1000, 1000, 900, 1100, 1)],
    [(0, 1000, 1200, 900, 1100, 1)],
    [(0, 1000, 1000, 900, 1100, float("nan"))],
])
def test_bad_times_ohlc_or_volume_rejected(tmp_path, rows):
    path = tmp_path / "bad.bi5"
    path.write_bytes(encoded(rows))
    with pytest.raises(MarketDataError):
        read_bid_m15(path, date(2026, 3, 30))


def test_partial_record_stream_rejected(tmp_path):
    path = tmp_path / "partial.bi5"
    path.write_bytes(lzma.compress(b"partial"))
    with pytest.raises(MarketDataError, match="record stream"):
        read_bid_m15(path, date(2026, 3, 30))

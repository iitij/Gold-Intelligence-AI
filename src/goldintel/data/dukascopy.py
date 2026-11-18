"""Decode XAUUSD legacy Dukascopy daily BID M1 files for clock diagnostics.

Layout reference: frozen aurum/data/dukascopy.py (24-byte O,C,L,H records,
UTC seconds from day start, XAUUSD integer price divisor 1000). No networking.
"""
from __future__ import annotations

import lzma
import math
import struct
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from goldintel.data.mt5_csv import MarketDataError

RECORD = struct.Struct(">IIIIIf")


def read_bid_m15(path: Path, utc_day: date) -> tuple[dict, dict]:
    compressed = path.read_bytes()
    if not compressed or len(compressed) > 1_000_000:
        raise MarketDataError("Empty or oversized Dukascopy daily file")
    decoder = lzma.LZMADecompressor(memlimit=64 * 1024 * 1024)
    try:
        raw = decoder.decompress(compressed, max_length=1440 * RECORD.size + 1)
    except lzma.LZMAError as exc:
        raise MarketDataError("Invalid Dukascopy LZMA") from exc
    if not decoder.eof or decoder.unused_data or not raw or len(raw) % RECORD.size:
        raise MarketDataError("Invalid daily candle record stream")
    day = datetime.combine(utc_day, time(), tzinfo=timezone.utc)
    minutes = {}
    previous = -1
    zero_volume = 0
    for seconds, open_, close, low, high, volume in RECORD.iter_unpack(raw):
        if (seconds <= previous or seconds >= 86400 or seconds % 60
                or not 0 < low <= min(open_, close) <= max(open_, close) <= high
                or not math.isfinite(volume) or volume < 0):
            raise MarketDataError("Invalid Dukascopy candle time, OHLC or volume")
        previous = seconds
        if volume == 0:
            zero_volume += 1
            continue
        minutes[day + timedelta(seconds=seconds)] = {
            name: Decimal(value) / 1000 for name, value in (
                ("open", open_), ("close", close), ("low", low), ("high", high),
            )
        }
    bars = {}
    incomplete = []
    for quarter in range(96):
        boundary = day + timedelta(minutes=quarter * 15)
        times = [boundary + timedelta(minutes=minute) for minute in range(15)]
        observed = [minutes[t] for t in times if t in minutes]
        if len(observed) != 15:
            incomplete.append({"nominal_utc_open": boundary.isoformat(), "active_minutes": len(observed)})
            continue
        bars[boundary] = {"open": observed[0]["open"], "close": observed[-1]["close"],
                          "low": min(row["low"] for row in observed),
                          "high": max(row["high"] for row in observed)}
    return bars, {
        "records_m1": len(raw) // RECORD.size, "zero_volume_minutes_excluded": zero_volume,
        "complete_m15": len(bars), "incomplete_or_inactive_m15": incomplete,
        "price_side": "BID", "integer_price_divisor": 1000,
        "time_interpretation": "legacy daily endpoint UTC day plus record seconds",
        "layout_reference": "vendor/snapshots/zero-was-here--tradingbot/aurum/data/dukascopy.py",
        "upstream_independence_verified": False, "training_ready": False,
    }

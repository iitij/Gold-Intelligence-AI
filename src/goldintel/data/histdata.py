"""Read documented HistData ASCII M1 Bid bars; retain incomplete M15 buckets."""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path
from zipfile import ZipFile

from goldintel.data.mt5_csv import MarketDataError


def read_m15(path: Path) -> tuple[dict, dict]:
    """Convert fixed EST (UTC-5, no DST) to UTC; exclude incomplete buckets.

    Schema and timezone: https://www.histdata.com/f-a-q/data-files-detailed-specification/
    This does not verify upstream provenance or historical broker UTC mapping.
    """
    with ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.endswith('.csv')]
        if len(names) != 1:
            raise MarketDataError('Expected exactly one CSV member')
        if archive.getinfo(names[0]).file_size > 50_000_000:
            raise MarketDataError('Reference sample exceeds size limit')
        text = archive.read(names[0]).decode('utf-8-sig')
    buckets = defaultdict(list)
    previous = None
    rows = 0
    for fields in csv.reader(StringIO(text), delimiter=';'):
        if len(fields) != 6:
            raise MarketDataError('Unexpected HistData M1 schema')
        try:
            t = datetime.strptime(fields[0], '%Y%m%d %H%M%S')
            prices = tuple(Decimal(v) for v in fields[1:5])
            volume = Decimal(fields[5])
        except (ValueError, InvalidOperation) as exc:
            raise MarketDataError('Invalid reference row') from exc
        if t.second or (previous is not None and t <= previous):
            raise MarketDataError('Duplicate, unordered or non-minute timestamp')
        o, h, low, c = prices
        if (any(not p.is_finite() or p <= 0 for p in prices) or
                not volume.is_finite() or volume < 0 or not low <= min(o, c) <= max(o, c) <= h):
            raise MarketDataError('Invalid reference OHLC or volume')
        previous = t
        utc = (t + timedelta(hours=5)).replace(tzinfo=timezone.utc)
        bucket = utc.replace(minute=utc.minute // 15 * 15)
        buckets[bucket].append((utc, prices))
        rows += 1
    if not rows:
        raise MarketDataError('Empty reference')
    complete, incomplete = {}, []
    for t, entries in sorted(buckets.items()):
        expected = [t + timedelta(minutes=i) for i in range(15)]
        if [e[0] for e in entries] != expected:
            incomplete.append({'utc_open': t.isoformat(), 'observed_minutes': len(entries)})
            continue
        complete[t] = {'open': entries[0][1][0], 'high': max(e[1][1] for e in entries),
                       'low': min(e[1][2] for e in entries), 'close': entries[-1][1][3]}
    return complete, {'rows_m1': rows, 'complete_m15': len(complete),
                      'incomplete_m15': incomplete, 'price_side': 'BID',
                      'source_timezone': 'FIXED_UTC_MINUS_5_NO_DST',
                      'broker_utc_verified': False, 'training_ready': False}

"""Audit HistData Bid/Ask ticks; no broker execution or cost assumptions."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from io import TextIOWrapper
from pathlib import Path
from zipfile import ZipFile

from goldintel.data.mt5_csv import MarketDataError


def audit_ticks(path: Path) -> dict:
    """Accept equal timestamps, reject backwards time and crossed/nonfinite quotes."""
    histograms: dict[str, Counter] = {}
    rows = equal_timestamps = 0
    previous = first = last = None
    max_gap_ms = 0
    with ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith('.csv')]
        if len(names) != 1 or archive.getinfo(names[0]).file_size > 512_000_000:
            raise MarketDataError('Expected one bounded tick CSV')
        with archive.open(names[0]) as raw, TextIOWrapper(raw, encoding='utf-8-sig') as text:
            for fields in csv.reader(text):
                if len(fields) != 4:
                    raise MarketDataError('Expected timestamp,Bid,Ask,volume')
                try:
                    stamp = fields[0]
                    if len(stamp) != 18:
                        raise ValueError('Expected millisecond timestamp')
                    t = datetime.strptime(stamp, '%Y%m%d %H%M%S%f')
                    bid, ask, volume = map(Decimal, fields[1:])
                except (ValueError, InvalidOperation) as exc:
                    raise MarketDataError('Invalid tick row') from exc
                if (any(not v.is_finite() for v in (bid, ask, volume)) or
                        bid <= 0 or ask < bid or volume < 0):
                    raise MarketDataError('Invalid or crossed quote')
                if previous is not None:
                    if t < previous:
                        raise MarketDataError('Backwards tick timestamp')
                    equal_timestamps += int(t == previous)
                    max_gap_ms = max(max_gap_ms, (t - previous) // timedelta(milliseconds=1))
                utc = (t + timedelta(hours=5)).replace(tzinfo=timezone.utc)
                first = first or utc
                last = utc
                histograms.setdefault(utc.date().isoformat(), Counter())[ask - bid] += 1
                rows += 1
                previous = t
    if not rows:
        raise MarketDataError('Empty tick file')
    daily = {}
    for day, histogram in sorted(histograms.items()):
        count = sum(histogram.values())
        cumulative = 0
        quantiles = {}
        for spread, n in sorted(histogram.items()):
            cumulative += n
            for label, numerator in [('p50', 50), ('p95', 95), ('p99', 99)]:
                if label not in quantiles and cumulative * 100 >= numerator * count:
                    quantiles[label] = str(spread)
        daily[day] = {'ticks': count, **quantiles, 'max': str(max(histogram)),
                      'zero_spread_ticks': histogram[Decimal(0)]}
    digest = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'source_sha256': digest.hexdigest(), 'ticks': rows,
            'first_utc': first.isoformat(), 'last_utc': last.isoformat(),
            'equal_timestamp_ticks': equal_timestamps, 'maximum_gap_ms': max_gap_ms,
            'source_timezone': 'FIXED_UTC_MINUS_5_NO_DST',
            'daily_spread_usd_per_ounce_tick_weighted_nearest_rank': daily,
            'upstream_independence_verified': False, 'broker_costs_verified': False,
            'training_ready': False, 'execution_ready': False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tick_zip', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit_ticks(args.tick_zip), indent=2))


if __name__ == '__main__':
    main()

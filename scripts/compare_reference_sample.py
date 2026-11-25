"""Reproduce exploratory comparisons on a common cohort under offset hypotheses."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from statistics import median

from goldintel.data.histdata import read_m15
from goldintel.data.mt5_csv import TIME_FORMAT, validate_mt5_csv


def compare(reference: Path, left: Path, right: Path, *, all_days: bool = False) -> dict:
    bars, quality = read_m15(reference)
    sources = {}
    feeds = {}
    for label, path in [('MetaQuotes', left), ('Headway', right)]:
        validation = validate_mt5_csv(path, expected_symbol='XAUUSD')
        with path.open(encoding='utf-8-sig', newline='') as stream:
            feeds[label] = {datetime.strptime(r['server_time'], TIME_FORMAT): Decimal(r['close'])
                            for r in csv.DictReader(stream)}
        if validate_mt5_csv(path, expected_symbol='XAUUSD') != validation:
            raise ValueError('Broker source changed during comparison')
        sources[label] = validation.source_sha256
    cohorts = defaultdict(list)
    for time in sorted(feeds['MetaQuotes'].keys() & feeds['Headway'].keys()):
        if all((time - timedelta(hours=offset)).replace(tzinfo=timezone.utc) in bars
               for offset in (2, 3)):
            cohorts[time.date().isoformat()].append(time)
    results = []
    for day in sorted(cohorts) if all_days else ['2026-03-03', '2026-03-09']:
        cohort = cohorts[day]
        for label, feed in feeds.items():
            for offset in (2, 3):
                differences = [feed[t] - bars[(t - timedelta(hours=offset)).replace(
                    tzinfo=timezone.utc)]['close'] for t in cohort]
                results.append({'broker': label, 'server_day': day,
                                'hypothetical_offset_hours': offset, 'matches': len(cohort),
                                'median_absolute_close_difference_usd':
                                str(median(abs(d) for d in differences)) if differences else None,
                                'mean_signed_close_difference_usd':
                                str(sum(differences) / len(differences)) if differences else None})
    return {'source_hashes': sources, 'reference_sha256': hashlib.sha256(
        reference.read_bytes()).hexdigest(), 'quality': quality, 'comparisons': results,
        'day_selection': 'all_available_common_reference_days' if all_days else 'two_original_diagnostic_days',
        'cohort_policy': 'Same server labels for both brokers and both offset hypotheses per day',
        'offsets_verified': False, 'broker_price_side_verified': False,
        'upstream_independence_verified': False, 'training_ready': False,
        'execution_ready': False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('metaquotes', type=Path)
    parser.add_argument('headway', type=Path)
    parser.add_argument('--all-days', action='store_true')
    args = parser.parse_args()
    print(json.dumps(compare(args.reference, args.metaquotes, args.headway, all_days=args.all_days), indent=2))


if __name__ == '__main__':
    main()

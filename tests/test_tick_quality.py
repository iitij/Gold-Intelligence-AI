"""Synthetic tick quality tests, unrelated to market performance."""
from zipfile import ZipFile

import pytest

from goldintel.data.mt5_csv import MarketDataError
from goldintel.data.tick_quality import audit_ticks


def sample(tmp_path, rows):
    path = tmp_path / 'ticks.zip'
    with ZipFile(path, 'w') as z:
        z.writestr('ticks.csv', '\n'.join(rows))
    return path


def test_bid_ask_spread_fixed_est_and_equal_timestamp_ticks(tmp_path):
    rows = ['20260309 100000000,5000,5000.2,0',
            '20260309 100000000,5000,5000.4,0',
            '20260309 100000001,5000,5001,0']
    report = audit_ticks(sample(tmp_path, rows))
    assert report['ticks'] == 3
    assert report['equal_timestamp_ticks'] == 1
    assert report['first_utc'] == '2026-03-09T15:00:00+00:00'
    daily = report['daily_spread_usd_per_ounce_tick_weighted_nearest_rank']['2026-03-09']
    assert daily['p50'] == '0.4'
    assert daily['p95'] == '1'
    assert not report['broker_costs_verified']
    assert not report['training_ready']


@pytest.mark.parametrize('rows', [
    ['20260309 100000000,5000,4999,0'],
    ['20260309 100000000,NaN,5001,0'],
    ['20260309 100000001,5000,5001,0', '20260309 100000000,5000,5001,0'],
    ['20260309 100000,5000,5001,0'], [],
])
def test_invalid_ticks_rejected(tmp_path, rows):
    with pytest.raises(MarketDataError):
        audit_ticks(sample(tmp_path, rows))

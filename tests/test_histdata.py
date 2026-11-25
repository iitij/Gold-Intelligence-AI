"""Synthetic checks for fixed EST, missing minutes and invalid reference prices."""
from zipfile import ZipFile

import pytest

from goldintel.data.histdata import read_m15
from goldintel.data.mt5_csv import MarketDataError


def archive(tmp_path, rows):
    path = tmp_path / 'sample.zip'
    with ZipFile(path, 'w') as z:
        z.writestr('sample.csv', '\n'.join(rows))
    return path


def test_fixed_est_in_march_and_incomplete_bucket_not_filled(tmp_path):
    rows = [f'20260309 10{i:02d}00;5000;5002;4999;5001;0' for i in range(16)]
    bars, report = read_m15(archive(tmp_path, rows))
    assert len(bars) == 1
    assert next(iter(bars)).isoformat() == '2026-03-09T15:00:00+00:00'
    assert report['incomplete_m15'][0]['observed_minutes'] == 1
    assert not report['training_ready']


@pytest.mark.parametrize('rows', [
    ['20260309 100000;5000;5002;4999;5001;0'] * 2,
    ['20260309 100000;5000;4998;4999;5001;0'],
    ['20260309 100000;NaN;5002;4999;5001;0'],
    [],
])
def test_bad_reference_rejected(tmp_path, rows):
    with pytest.raises(MarketDataError):
        read_m15(archive(tmp_path, rows))

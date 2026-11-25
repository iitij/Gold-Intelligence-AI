"""Keep reference-offset diagnostics on an identical cohort."""
import csv
import importlib.util
from pathlib import Path
from zipfile import ZipFile

from goldintel.data.mt5_csv import COLUMNS

spec = importlib.util.spec_from_file_location(
    'reference_sample', Path(__file__).resolve().parents[1] / 'scripts/compare_reference_sample.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_incomplete_reference_and_unmatched_broker_labels_excluded(tmp_path):
    reference = tmp_path / 'reference.zip'
    rows = [f'20260303 {hour:02d}{minute:02d}00;5000;5002;4999;5001;0'
            for hour in (0, 1) for minute in range(15)]
    rows.append('20260303 001500;5000;5002;4999;5001;0')
    with ZipFile(reference, 'w') as z:
        z.writestr('sample.csv', '\n'.join(sorted(rows)))
    paths = []
    for name, times in [('left', ['08:00:00', '08:15:00']), ('right', ['08:00:00'])]:
        p = tmp_path / (name + '.csv')
        with p.open('w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(COLUMNS)
            for t in times:
                writer.writerow(['XAUUSD', 'M15', '2026.03.03 ' + t,
                                 5000, 5002, 4999, 5001, 10, 20, 0])
        paths.append(p)
    report = module.compare(reference, *paths)
    march3 = [r for r in report['comparisons'] if r['server_day'] == '2026-03-03']
    assert {r['matches'] for r in march3} == {1}
    assert {r['median_absolute_close_difference_usd'] for r in march3} == {'0'}
    assert not report['offsets_verified']
    assert not report['training_ready']
    full = module.compare(reference, *paths, all_days=True)
    assert {row['server_day'] for row in full['comparisons']} == {'2026-03-03'}
    assert len(full['comparisons']) == 4
    assert {row['matches'] for row in full['comparisons']} == {1}

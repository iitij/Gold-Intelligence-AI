"""Matched exploratory distribution scores with a training-only return baseline."""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from forecast_distribution_metrics import (
    fit_return_quantiles,
    float32_reference_errors,
    pinball_losses,
    reconstructed_crps,
    weighted_interval_score,
)

LEVELS = [.01, .05, .1, .15, .2, .25, .3, .35, .4, .45, .5,
          .55, .6, .65, .7, .75, .8, .85, .9, .95, .99]
WEIGHTS_SHA = 'ddcda3c7508bf2528087723e98a20707cc04b7f370ae275a9fd88078ddba4f42'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_panel(path, expected_sha):
    if digest(path) != expected_sha:
        raise ValueError('Panel fingerprint differs from saved NHITS experiment')
    frame = pd.read_csv(path, parse_dates=['ds'])
    if (frame.empty or frame.ds.dt.tz is not None or frame.ds.isna().any()
            or not frame.ds.is_monotonic_increasing or frame.ds.duplicated().any()
            or not np.isfinite(frame.y).all() or (frame.y <= 0).any()
            or set(frame.split) != {'train', 'validation', 'test'}):
        raise ValueError('Invalid native-time forecast panel')
    for _, group in frame.groupby('unique_id', sort=False):
        if (len(group) < 80 or group.split.nunique() != 1
                or not group.ds.diff().dropna().eq(pd.Timedelta(minutes=15)).all()):
            raise ValueError('Forecast segment is incomplete or crosses a gap/split')
    if (not (frame.loc[frame.split.eq('train'), 'ds'] < pd.Timestamp('2026-01-01')).all()
            or not frame.loc[frame.split.eq('validation'), 'ds'].between(
                pd.Timestamp('2026-01-01'), pd.Timestamp('2026-04-01'), inclusive='left').all()
            or not (frame.loc[frame.split.eq('test'), 'ds'] >= pd.Timestamp('2026-04-01')).all()):
        raise ValueError('Panel split chronology differs from original experiment')
    return frame


def score_summary(y, predictions):
    lower, median, upper = (predictions[:, LEVELS.index(q)] for q in (.1, .5, .9))
    return {
        'rows': len(y), 'wis': float(weighted_interval_score(y, predictions, LEVELS).mean()),
        'crps_bounded_linear_reconstruction': float(reconstructed_crps(y, predictions, LEVELS).mean()),
        'median_mae': float(np.abs(y - median).mean()),
        'coverage_80': float(((y >= lower) & (y <= upper)).mean()),
        'width_80': float((upper - lower).mean()),
        'coverage_98': float(((y >= predictions[:, 0]) & (y <= predictions[:, -1])).mean()),
        'pinball_by_level': dict(zip(map(str, LEVELS),
                                     pinball_losses(y, predictions, LEVELS).mean(axis=0).tolist(), strict=True)),
        'fraction_outcomes_at_or_below_quantile': dict(zip(map(str, LEVELS),
            (y[:, None] <= predictions).mean(axis=0).tolist(), strict=True)),
    }


def weekly_paired_difference(actual, difference):
    weeks = actual.ds.dt.to_period('W-SUN').astype(str)
    frame = pd.DataFrame({'week': weeks.to_numpy(), 'difference': difference})
    grouped = frame.groupby('week').difference.agg(['sum', 'count'])
    output = {'definition': 'Chronos WIS minus empirical-return baseline WIS; negative favors Chronos',
              'native_calendar_weeks': len(grouped), 'mean_difference': float(difference.mean()),
              'weekly': [{'week': name, 'sum': float(row['sum']), 'count': int(row['count'])}
                         for name, row in grouped.iterrows()],
              'ci95': None, 'seed': 42, 'resamples': 2000}
    if len(grouped) >= 8:
        indices = np.random.default_rng(42).integers(0, len(grouped), (2000, len(grouped)))
        values = grouped['sum'].to_numpy()[indices].sum(axis=1)
        counts = grouped['count'].to_numpy()[indices].sum(axis=1)
        output['ci95'] = np.quantile(values / counts, [.025, .975]).tolist()
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--panel', type=Path, required=True)
    parser.add_argument('--nhits-reference', type=Path, required=True)
    parser.add_argument('--chronos-model', type=Path, required=True)
    parser.add_argument('--chronos-reference', type=Path, required=True)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from reproduce_forecast_runtime import verify_runtime

    packages = verify_runtime(args.lock)
    model_config = args.chronos_model / 'config.json'
    if json.loads(model_config.read_text())['chronos_config']['quantiles'] != LEVELS:
        raise ValueError('Chronos quantile grid differs from this analysis')
    if digest(args.chronos_model / 'model.safetensors') != WEIGHTS_SHA:
        raise ValueError('Chronos weights differ from the pinned revision')
    original = json.loads(args.nhits_reference.read_text())
    if set(p.name for p in args.panel.glob('*.csv')) != set(original['feeds']):
        raise ValueError('Panel feed set differs from original forecast experiment')
    panels = {name: load_panel(args.panel / name, conf['panel_sha256'])
              for name, conf in original['feeds'].items()}
    args.output.mkdir()
    plan = {
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'study_type': 'Exploratory new metric analysis of previously inspected historical outcomes',
        'primary_metric': 'validation WIS, lower is better', 'quantile_levels': LEVELS,
        'context_bars': 64, 'horizon_bars': 16, 'cross_learning': False,
        'candidates': ['Chronos-2', 'empirical_training_returns', 'point_persistence'],
        'baseline_fit': 'All training-only origins with 64 completed context bars and all 16 outcomes',
        'baseline_prediction': 'origin close times (1 + per-step training return quantiles)',
        'quantile_crossing_policy': 'Sort each forecast quantile row; report original crossing fraction',
        'legacy_comparison_precision': 'Exact float32 round trip of shortest-decimal CSV reference values',
        'crps_definition': 'Exact CRPS only for linear quantile interpolation and constant extreme tails',
        'bootstrap': '2000 native-calendar weekly cluster resamples, seed 42; marginal descriptive intervals',
        'script_sha256': digest(Path(__file__)),
        'metrics_script_sha256': digest(Path(__file__).with_name('forecast_distribution_metrics.py')),
        'runtime_lock_sha256': digest(args.lock), 'packages': packages,
        'weights_sha256': WEIGHTS_SHA, 'model_config_sha256': digest(model_config),
        'nhits_reference_sha256': digest(args.nhits_reference),
        'panel_sha256': {name: digest(args.panel / name) for name in panels},
        'approved_for_trading': False,
    }
    plan_path = args.output / 'analysis-plan.json'
    plan_path.write_text(json.dumps(plan, indent=2) + '\n')
    # The plan above is persisted before inference and scoring; outcomes were previously inspected.
    import torch
    from chronos import Chronos2Pipeline

    torch.set_num_threads(2)
    pipeline = Chronos2Pipeline.from_pretrained(str(args.chronos_model), device_map='cpu')
    report = {'status': 'complete', 'analysis_plan_sha256': digest(plan_path),
              'primary_metric': plan['primary_metric'],
              'feeds': {}, 'approved_for_trading': False,
              'limitations': [
                  'Previously inspected historical outcomes and new metric selection; exploratory only',
                  'Chronos pretraining overlap with historical dates remains unverified',
                  'Native broker time is not approved UTC; weekly grouping uses native calendar',
                  'CRPS uses bounded reconstructed quantiles, not an identified full Chronos CDF',
                  'Baseline distribution drift and within-week dependence remain possible',
                  'Intervals are marginal, not corrected for repeated experiments',
                  'Inclusive quantile coverage can reflect ties/atoms',
                  'Price scores exclude spread, fees, latency, financing and portfolio execution',
              ]}
    for name, frame in sorted(panels.items()):
        training = frame.loc[frame.split.eq('train')]
        quantiles, origins = fit_return_quantiles(training, LEVELS)
        fitted = {'training_rows': len(training), 'complete_training_origins': origins,
                  'last_training_outcome_native': str(training.ds.max()),
                  'return_quantiles_by_step': quantiles.tolist(), 'levels': LEVELS}
        (args.output / f'{Path(name).stem}-baseline.json').write_text(json.dumps(fitted, indent=2) + '\n')
        feed_report = {'baseline_fit': fitted, 'splits': {}}
        for split in ('validation', 'test'):
            held = frame.loc[frame.split.eq(split)]
            context = held.groupby('unique_id', group_keys=False).head(-16)
            context = context.groupby('unique_id', group_keys=False).tail(64)
            actual = held.groupby('unique_id', group_keys=False).tail(16).copy()
            actual['step'] = actual.groupby('unique_id').cumcount() + 1
            anchors = context.groupby('unique_id').agg(origin=('ds', 'last'), close=('y', 'last'))
            actual['origin_native'] = actual.unique_id.map(anchors.origin)
            actual['origin_close'] = actual.unique_id.map(anchors.close)
            if not actual.ds.eq(actual.origin_native + pd.to_timedelta(actual.step * 15, unit='min')).all():
                raise ValueError('Outcome dates do not match forecast origins')
            started = time.perf_counter()
            forecast = pipeline.predict_df(context[['unique_id', 'ds', 'y']], prediction_length=16,
                quantile_levels=LEVELS, id_column='unique_id', timestamp_column='ds', target='y',
                context_length=64, cross_learning=False, freq='15min')
            wall_seconds = time.perf_counter() - started
            output_name = f'{Path(name).stem}-{split}'
            forecast.to_csv(args.output / f'{output_name}-quantiles.csv', index=False)
            joined = actual.merge(forecast, on=['unique_id', 'ds'], validate='one_to_one')
            if len(joined) != len(actual) or len(forecast) != len(actual):
                raise ValueError('Forecast/outcome boundaries differ')
            legacy_path = args.chronos_reference / f'{output_name}-predictions.csv'
            legacy = pd.read_csv(legacy_path, parse_dates=['ds'])
            check = forecast.merge(legacy, on=['unique_id', 'ds', 'target_name'],
                                   validate='one_to_one', suffixes=('', '_legacy'))
            errors = dict(zip(['0.1', '0.5', '0.9'], float32_reference_errors(
                check[['0.1', '0.5', '0.9']],
                check[['0.1_legacy', '0.5_legacy', '0.9_legacy']]).tolist(), strict=True))
            if len(check) != len(forecast) or any(v != 0 for v in errors.values()):
                raise ValueError('Existing Chronos three-quantile forecasts changed')
            raw = joined[list(map(str, LEVELS))].to_numpy(dtype=float)
            candidates = {
                'Chronos-2': np.sort(raw, axis=1),
                'empirical_training_returns': joined.origin_close.to_numpy()[:, None]
                    * (1 + quantiles[joined.step.to_numpy() - 1]),
                'point_persistence': np.repeat(joined.origin_close.to_numpy()[:, None], len(LEVELS), axis=1),
            }
            y = joined.y.to_numpy()
            results = {}
            ledgers = {}
            for candidate, predictions in candidates.items():
                results[candidate] = score_summary(y, predictions)
                results[candidate]['per_step'] = {
                    str(step): score_summary(y[joined.step.eq(step)], predictions[joined.step.eq(step)])
                    for step in range(1, 17)}
                ledger = joined[['unique_id', 'ds', 'step', 'origin_native', 'y']].copy()
                ledger['wis'] = weighted_interval_score(y, predictions, LEVELS)
                ledger['crps_reconstructed'] = reconstructed_crps(y, predictions, LEVELS)
                ledger.to_csv(args.output / f'{output_name}-{candidate}-scores.csv', index=False)
                ledgers[candidate] = ledger
            feed_report['splits'][split] = {
                'candidates': results, 'chronos_inference_wall_seconds': wall_seconds,
                'chronos_original_crossing_row_fraction': float((np.diff(raw, axis=1) < 0).any(axis=1).mean()),
                'legacy_prediction_sha256': digest(legacy_path),
                'legacy_quantile_max_absolute_errors': errors,
                'paired_chronos_minus_empirical_wis': weekly_paired_difference(joined,
                    (ledgers['Chronos-2'].wis - ledgers['empirical_training_returns'].wis).to_numpy()),
            }
        selected = min(feed_report['splits']['validation']['candidates'],
                       key=lambda candidate: feed_report['splits']['validation']['candidates'][candidate]['wis'])
        feed_report['selected_by_validation_wis'] = selected
        feed_report['selected_test_wis'] = feed_report['splits']['test']['candidates'][selected]['wis']
        report['feeds'][name] = feed_report
    (args.output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    files = {p.name: digest(p) for p in sorted(args.output.iterdir()) if p.is_file()}
    (args.output / 'files.sha256.json').write_text(json.dumps(files, indent=2) + '\n')
    print('PASS: matched 21-quantile forecasts and training-only baselines scored for both feeds')


if __name__ == '__main__':
    main()

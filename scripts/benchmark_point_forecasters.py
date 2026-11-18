"""Compare common point outcomes and time each CPU forecaster in an isolated process."""
import argparse
import hashlib
import json
import resource
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from evaluate_forecast_distributions import load_panel
from forecast_point_evaluation import (
    held_out_inputs,
    match_point_predictions,
    outcome_digest,
    paired_weekly_mae,
    point_metrics,
)
from reproduce_forecast_runtime import verify_runtime


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def worker(spec_path, output):
    spec = json.loads(spec_path.read_text())
    for path, expected in spec['fingerprints'].items():
        if digest(path) != expected:
            raise ValueError('Worker input or code fingerprint differs')
    packages = verify_runtime(Path(spec['lock']))
    frame = load_panel(Path(spec['panel']), spec['fingerprints'][spec['panel']])
    output.mkdir()
    started = time.perf_counter()
    kind = spec['kind']
    model = None
    parameters = None
    if kind == 'saved-neural':
        import torch
        from neuralforecast import NeuralForecast

        torch.set_num_threads(2)
        model = NeuralForecast.load(path=spec['checkpoint'])
        parameters = sum(p.numel() for p in model.models[0].parameters())
    elif kind == 'chronos':
        import torch
        from chronos import Chronos2Pipeline

        torch.set_num_threads(2)
        model = Chronos2Pipeline.from_pretrained(spec['checkpoint'], device_map='cpu')
    elif kind != 'persistence':
        raise ValueError('Unknown fixed worker kind')
    load_wall = time.perf_counter() - started
    original = json.loads(Path(spec['reference']).read_text()) if spec['reference'] else None
    result = {'candidate': spec['candidate'], 'feed': spec['feed'], 'splits': {},
              'spec_sha256': digest(spec_path), 'installed_package_count': len(packages),
              'load_including_neural_import_wall_seconds': load_wall,
              'model_parameter_count': parameters}
    for split in ('validation', 'test'):
        context, actual = held_out_inputs(frame, split)

        def predict():
            if kind == 'saved-neural':
                return model.predict(df=context)
            if kind == 'chronos':
                return model.predict_df(context, prediction_length=16, quantile_levels=[.1, .5, .9],
                    id_column='unique_id', timestamp_column='ds', target='y', context_length=64,
                    cross_learning=False, freq='15min')
            return actual[['unique_id', 'ds', 'origin_price']].rename(columns={'origin_price': 'persistence'})

        # Warm-up excluded from timing, retained as a reference for all repeated predictions.
        ledger = match_point_predictions(actual, predict(), spec['column'])
        durations, max_error = [], 0.
        for _ in range(5):
            began = time.perf_counter()
            predicted = predict()
            durations.append(time.perf_counter() - began)
            repeated = match_point_predictions(actual, predicted, spec['column'])
            max_error = max(max_error, float((ledger.prediction - repeated.prediction).abs().max()))
        if max_error > 1e-6:
            raise ValueError('Repeated point forecasts differ')
        metrics = point_metrics(ledger)
        if original:
            reference = original['feeds'][spec['feed']][split]
            if (metrics['rows'] != reference['rows']
                    or abs(metrics['mae_price'] - reference['mae_price']) > 1e-6
                    or abs(metrics['persistence_mae_price'] - reference['persistence_mae_price']) > 1e-6):
                raise ValueError('Point scores differ from original model report')
        ledger_path = output / f'{split}-predictions.csv'
        ledger.to_csv(ledger_path, index=False)
        result['splits'][split] = {
            **metrics, 'outcome_sha256': outcome_digest(actual),
            'predictions_sha256': digest(ledger_path),
            'repeat_max_absolute_prediction_error': max_error,
            'paired_weekly_mae_vs_persistence': paired_weekly_mae(ledger),
            'batch_timing': {'warmups': 1, 'repetitions': 5, 'seconds': durations,
                             'median_seconds': float(np.median(durations)),
                             'p95_seconds': float(np.quantile(durations, .95)),
                             'scope': 'One batch of all origins; model API call; excludes matching and scoring'},
        }
    result['isolated_process_peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result['isolated_process_cpu_seconds'] = resource.getrusage(resource.RUSAGE_SELF).ru_utime + resource.getrusage(resource.RUSAGE_SELF).ru_stime
    write_json(output / 'report.json', result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker-spec', type=Path)
    parser.add_argument('--worker-output', type=Path)
    for name in ('panel', 'nhits-200', 'nhits-500', 'nbeatsx', 'chronos-model',
                 'chronos-reference', 'lock', 'output'):
        parser.add_argument('--' + name, type=Path)
    args = parser.parse_args()
    if args.worker_spec:
        if args.worker_output is None:
            parser.error('--worker-output is required')
        worker(args.worker_spec, args.worker_output)
        return
    if any(getattr(args, name) is None for name in ('panel', 'nhits_200', 'nhits_500', 'nbeatsx',
              'chronos_model', 'chronos_reference', 'lock', 'output')):
        parser.error('All parent experiment inputs and --output are required')
    packages = verify_runtime(args.lock)
    reference = json.loads((args.nhits_200 / 'report.json').read_text())
    if set(p.name for p in args.panel.glob('*.csv')) != set(reference['feeds']):
        raise ValueError('Panel feed set differs')
    for name, config in reference['feeds'].items():
        load_panel(args.panel / name, config['panel_sha256'])
    args.output.mkdir()
    fixed = [
        ('NHITS-200', 'saved-neural', args.nhits_200, 'NHITS'),
        ('NHITS-500', 'saved-neural', args.nhits_500, 'NHITS'),
        ('NBEATSx-200', 'saved-neural', args.nbeatsx, 'NBEATSx'),
        ('Chronos-2', 'chronos', args.chronos_model, '0.5'),
        ('persistence', 'persistence', None, 'persistence'),
    ]
    plan = {'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'study_type': 'Exploratory saved-model point comparison on inspected historical dates',
            'selection': 'validation price MAE', 'packages': packages,
            'lock_sha256': digest(args.lock), 'script_sha256': digest(Path(__file__)),
            'candidates': [row[0] for row in fixed], 'cpu_threads': 2,
            'benchmark': 'Separate subprocess for each model/feed; warm-up then five CPU batches per split',
            'approved_for_trading': False}
    write_json(args.output / 'analysis-plan.json', plan)
    report = {'status': 'complete', 'analysis_plan_sha256': digest(args.output / 'analysis-plan.json'),
              'feeds': {}, 'approved_for_trading': False,
              'limitations': ['Previously inspected historical outcomes; no untouched holdout',
                  'Marginal native-week bootstrap intervals are not corrected for repeated comparisons',
                  'RSS is complete isolated-process high water, including imports, both splits and allocators',
                  'Batch API timings are single-host observations and exclude loading/data read/scoring',
                  'Chronos returns three quantiles; other model APIs return one point per outcome',
                  'NBEATSx receives no exogenous macro/news inputs',
                  'Native broker chronology remains separate from approved UTC',
                  'Price scores exclude all trading execution costs and constraints']}
    for feed in sorted(reference['feeds']):
        summaries = {}
        outcome_hashes = {}
        for candidate, kind, root, column in fixed:
            checkpoint = root / Path(feed).stem if kind == 'saved-neural' else root
            original_report = root / 'report.json' if kind == 'saved-neural' else (
                args.chronos_reference / 'report.json' if kind == 'chronos' else None)
            if kind == 'chronos' and digest(checkpoint / 'model.safetensors') != json.loads(
                    original_report.read_text())['weights_sha256']:
                raise ValueError('Chronos weights differ from the pinned original report')
            fingerprint_paths = [args.panel / feed, args.lock, Path(__file__),
                Path(__file__).with_name('forecast_point_evaluation.py'),
                Path(__file__).with_name('evaluate_forecast_distributions.py')]
            if original_report:
                fingerprint_paths.append(original_report)
            if checkpoint:
                fingerprint_paths += [p for p in checkpoint.iterdir() if p.is_file() and (
                    p.name == 'configuration.json' or p.name == 'config.json' or p.suffix == '.safetensors')]
            spec = {'candidate': candidate, 'kind': kind, 'checkpoint': str(checkpoint) if checkpoint else None,
                    'column': column, 'reference': str(original_report) if original_report else None,
                    'feed': feed, 'panel': str(args.panel / feed), 'lock': str(args.lock),
                    'fingerprints': {str(p): digest(p) for p in fingerprint_paths}}
            stem = f'{Path(feed).stem}-{candidate}'
            spec_path = args.output / f'{stem}-spec.json'
            write_json(spec_path, spec)
            worker_output = args.output / stem
            began = time.perf_counter()
            with (args.output / f'{stem}.log').open('w') as log:
                subprocess.run([sys.executable, str(Path(__file__)), '--worker-spec', str(spec_path),
                                '--worker-output', str(worker_output)], stdout=log, stderr=subprocess.STDOUT,
                               check=True)
            summary = json.loads((worker_output / 'report.json').read_text())
            if summary['spec_sha256'] != digest(spec_path):
                raise ValueError('Worker result does not match spec')
            summary['subprocess_total_wall_seconds'] = time.perf_counter() - began
            for split, metrics in summary['splits'].items():
                if split in outcome_hashes and outcome_hashes[split] != metrics['outcome_sha256']:
                    raise ValueError('Candidate outcome identities/values differ')
                outcome_hashes[split] = metrics['outcome_sha256']
            summaries[candidate] = summary
        selected = min(summaries, key=lambda name: summaries[name]['splits']['validation']['mae_price'])
        report['feeds'][feed] = {'candidates': summaries, 'common_outcome_sha256': outcome_hashes,
                                'selected_by_validation_mae': selected,
                                'selected_test_mae': summaries[selected]['splits']['test']['mae_price']}
    write_json(args.output / 'report.json', report)
    write_json(args.output / 'files.sha256.json', {str(p.relative_to(args.output)): digest(p)
               for p in sorted(args.output.rglob('*')) if p.is_file()})
    print('PASS: five point candidates matched by outcome identity; ten isolated CPU workers completed')


if __name__ == '__main__':
    main()

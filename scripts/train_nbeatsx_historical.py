"""Fit fixed-setting CPU NBEATSx without exogenous variables on existing panels."""
import argparse
import hashlib
import json
import platform
import resource
import time
from datetime import datetime, timezone
from pathlib import Path

from evaluate_forecast_distributions import load_panel
from forecast_point_evaluation import (
    held_out_inputs,
    match_point_predictions,
    outcome_digest,
    point_metrics,
)
from reproduce_forecast_runtime import verify_runtime


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--panel', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    packages = verify_runtime(args.lock)
    # Ray exposes bundled metadata on sys.path during import. Check the installed
    # environment first, as in the saved forecast runtime reproduction runner.
    import psutil
    import torch
    from neuralforecast import NeuralForecast
    from neuralforecast.models import NBEATSx

    original = json.loads(args.reference.read_text())
    if set(p.name for p in args.panel.glob('*.csv')) != set(original['feeds']):
        raise ValueError('Panel feed set differs from existing forecast experiment')
    panels = {name: load_panel(args.panel / name, config['panel_sha256'])
              for name, config in original['feeds'].items()}
    args.output.mkdir()
    torch.set_num_threads(2)
    parameters = {
        'h': 16, 'input_size': 64, 'max_steps': 200, 'scaler_type': 'standard',
        'random_seed': 42, 'accelerator': 'cpu', 'devices': 1,
        'enable_progress_bar': False, 'logger': False, 'enable_checkpointing': False,
        'stack_types': ['identity', 'trend', 'seasonality'], 'n_blocks': [1, 1, 1],
        'mlp_units': [[512, 512], [512, 512], [512, 512]], 'learning_rate': .001,
        'num_lr_decays': 3, 'batch_size': 32, 'windows_batch_size': 1024,
        'early_stop_patience_steps': -1, 'val_check_steps': 100,
    }
    plan = {
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'study_type': 'Exploratory fixed-setting additional model on previously inspected dates',
        'parameters': parameters, 'exogenous_variables': [],
        'loss': 'MAE', 'no_early_stopping': True, 'primary_selection': 'validation price MAE',
        'script_sha256': digest(Path(__file__)),
        'evaluation_helper_sha256': digest(Path(__file__).with_name('forecast_point_evaluation.py')),
        'panel_loader_sha256': digest(Path(__file__).with_name('evaluate_forecast_distributions.py')),
        'lock_sha256': digest(args.lock), 'packages': packages,
        'reference_sha256': digest(args.reference),
        'panel_sha256': {name: digest(args.panel / name) for name in panels},
        'host': {'python': platform.python_version(), 'system': platform.system(),
                 'machine': platform.machine(), 'logical_cpus': psutil.cpu_count(),
                 'physical_cpus': psutil.cpu_count(logical=False),
                 'memory_total_bytes': psutil.virtual_memory().total,
                 'torch_threads': torch.get_num_threads(),
                 'torch_interop_threads': torch.get_num_interop_threads(),
                 'torch_cuda_available': torch.cuda.is_available()},
        'approved_for_trading': False,
    }
    plan_path = args.output / 'analysis-plan.json'
    plan_path.write_text(json.dumps(plan, indent=2) + '\n')
    report = {'status': 'complete', 'model': 'NBEATSx', 'steps': 200,
              'context': 64, 'horizon': 16, 'analysis_plan_sha256': digest(plan_path),
              'exogenous_variables': [], 'feeds': {}, 'approved_for_trading': False,
              'limitations': ['Previously inspected historical outcomes; exploratory only',
                             'NBEATSx uses price history only; macro/news exogenous inputs are not supplied',
                             'Price accuracy excludes execution costs',
                             'CPU resource readings are host/process observations, not general guarantees',
                             'Fixed-setting training is not a comprehensive hyperparameter search']}
    for name, frame in sorted(panels.items()):
        training = frame.loc[frame.split.eq('train'), ['unique_id', 'ds', 'y']]
        model = NeuralForecast(models=[NBEATSx(**parameters)], freq='15min')
        started, cpu_started = time.perf_counter(), time.process_time()
        model.fit(df=training)
        result = {'panel_sha256': digest(args.panel / name), 'training_rows': len(training),
                  'last_training_outcome_native': str(training.ds.max()),
                  'fit_wall_seconds': time.perf_counter() - started,
                  'fit_process_cpu_seconds': time.process_time() - cpu_started,
                  'process_high_water_rss_kib_after_fit': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  'model_parameter_count': sum(p.numel() for p in model.models[0].parameters())}
        checkpoint = args.output / Path(name).stem
        model.save(path=str(checkpoint), overwrite=False, save_dataset=False)
        result['model_sha256'] = {p.name: digest(p) for p in sorted(checkpoint.iterdir()) if p.is_file()}
        reloaded = NeuralForecast.load(path=str(checkpoint))
        for split in ('validation', 'test'):
            context, actual = held_out_inputs(frame, split)
            predictions = model.predict(df=context)
            ledger = match_point_predictions(actual, predictions, 'NBEATSx')
            repeated = match_point_predictions(actual, reloaded.predict(df=context), 'NBEATSx')
            max_error = float((ledger.prediction - repeated.prediction).abs().max())
            if max_error > 1e-6:
                raise ValueError('Reloaded NBEATSx forecasts differ')
            output = args.output / f'{Path(name).stem}-{split}-predictions.csv'
            ledger.to_csv(output, index=False)
            result[split] = {**point_metrics(ledger), 'outcome_sha256': outcome_digest(actual),
                             'reload_max_absolute_prediction_error': max_error,
                             'predictions_sha256': digest(output)}
        report['feeds'][name] = result
    (args.output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    manifest = {str(p.relative_to(args.output)): digest(p)
                for p in sorted(args.output.rglob('*')) if p.is_file()}
    (args.output / 'files.sha256.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('PASS: fixed CPU NBEATSx trained and saved-model forecasts reproduced for both feeds')


if __name__ == '__main__':
    main()

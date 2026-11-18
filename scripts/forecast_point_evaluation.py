"""Match saved point forecasts to causal panel origins and common outcomes."""
import hashlib

import numpy as np
import pandas as pd


def held_out_inputs(frame, split):
    if split not in {'validation', 'test'}:
        raise ValueError('Only held-out splits may be evaluated')
    held = frame.loc[frame.split.eq(split)]
    if held.empty:
        raise ValueError('No held-out rows')
    for _, group in held.groupby('unique_id', sort=False):
        if (len(group) < 80 or group.ds.isna().any()
                or not group.ds.diff().dropna().eq(pd.Timedelta(minutes=15)).all()):
            raise ValueError('Held-out segment has insufficient context or a time gap')
    context = held.groupby('unique_id', group_keys=False).head(-16)
    context = context.groupby('unique_id', group_keys=False).tail(64)
    actual = held.groupby('unique_id', group_keys=False).tail(16).copy()
    actual['step'] = actual.groupby('unique_id').cumcount() + 1
    origins = context.groupby('unique_id').agg(origin_native=('ds', 'last'), origin_price=('y', 'last'))
    actual['origin_native'] = actual.unique_id.map(origins.origin_native)
    actual['origin_price'] = actual.unique_id.map(origins.origin_price)
    if not actual.ds.eq(actual.origin_native + pd.to_timedelta(actual.step * 15, unit='min')).all():
        raise ValueError('Held-out outcomes do not follow the available context')
    actual = actual[['unique_id', 'ds', 'origin_native', 'step', 'y', 'origin_price']]
    if actual.duplicated(['unique_id', 'ds']).any():
        raise ValueError('Duplicate forecast outcomes')
    return context[['unique_id', 'ds', 'y']], actual.reset_index(drop=True)


def outcome_digest(actual):
    return hashlib.sha256(actual.to_csv(index=False).encode()).hexdigest()


def match_point_predictions(actual, predicted, column):
    keys = ['unique_id', 'ds']
    if len(predicted) != len(actual) or predicted.duplicated(keys).any():
        raise ValueError('Forecast keys or row count differ')
    joined = actual.merge(predicted[keys + [column]], on=keys, validate='one_to_one')
    if len(joined) != len(actual):
        raise ValueError('Forecast outcome identities differ')
    joined = joined.rename(columns={column: 'prediction'})
    if not np.isfinite(joined[['y', 'origin_price', 'prediction']]).all().all():
        raise ValueError('Forecast prices must be finite')
    joined['absolute_error'] = (joined.prediction - joined.y).abs()
    joined['persistence_absolute_error'] = (joined.origin_price - joined.y).abs()
    return joined


def point_metrics(ledger):
    return {
        'rows': len(ledger), 'segments': ledger.unique_id.nunique(),
        'mae_price': float(ledger.absolute_error.mean()),
        'rmse_price': float(np.sqrt(((ledger.prediction - ledger.y)**2).mean())),
        'persistence_mae_price': float(ledger.persistence_absolute_error.mean()),
        'direction_accuracy': float(((ledger.prediction > ledger.origin_price)
                                     == (ledger.y > ledger.origin_price)).mean()),
    }


def paired_weekly_mae(ledger):
    frame = pd.DataFrame({'week': ledger.ds.dt.to_period('W-SUN').astype(str),
                          'difference': ledger.absolute_error - ledger.persistence_absolute_error})
    grouped = frame.groupby('week').difference.agg(['sum', 'count'])
    output = {'definition': 'model absolute error minus persistence absolute error; negative favors model',
              'native_calendar_weeks': len(grouped), 'mean_difference': float(frame.difference.mean()),
              'ci95': None, 'resamples': 2000, 'seed': 42}
    if len(grouped) >= 8:
        indices = np.random.default_rng(42).integers(0, len(grouped), (2000, len(grouped)))
        differences = grouped['sum'].to_numpy()[indices].sum(axis=1)
        counts = grouped['count'].to_numpy()[indices].sum(axis=1)
        output['ci95'] = np.quantile(differences / counts, [.025, .975]).tolist()
    return output

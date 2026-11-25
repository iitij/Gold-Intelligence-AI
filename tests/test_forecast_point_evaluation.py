"""Verify outcome identities and future-perturbation invariants of forecast panels."""
import pytest

np = pytest.importorskip('numpy')
pd = pytest.importorskip('pandas')

from scripts.forecast_point_evaluation import (  # noqa: E402
    held_out_inputs,
    match_point_predictions,
    outcome_digest,
    point_metrics,
)


def panel():
    return pd.DataFrame({'unique_id': ['a'] * 80,
                         'ds': pd.date_range('2026-01-02', periods=80, freq='15min'),
                         'y': np.arange(80, dtype=float) + 2000,
                         'split': ['test'] * 80})


def test_future_perturbation_preserves_context_and_origins_but_changes_outcome_hash():
    frame = panel()
    context, actual = held_out_inputs(frame, 'test')
    frame.loc[64:, 'y'] *= 10
    context_after, altered = held_out_inputs(frame, 'test')
    pd.testing.assert_frame_equal(context, context_after)
    assert len(context) == 64 and len(actual) == 16
    assert context.ds.max() < actual.ds.min()
    assert altered.origin_price.eq(2063).all()
    assert outcome_digest(actual) != outcome_digest(altered)


def test_same_row_count_with_shifted_outcome_identity_is_rejected():
    _, actual = held_out_inputs(panel(), 'test')
    predicted = actual[['unique_id', 'ds', 'y']].rename(columns={'y': 'model'})
    predicted.loc[0, 'ds'] += pd.Timedelta(days=1)
    with pytest.raises(ValueError, match='identities differ'):
        match_point_predictions(actual, predicted, 'model')


def test_shuffled_predictions_are_matched_by_identity_and_scored_correctly():
    _, actual = held_out_inputs(panel(), 'test')
    predictions = actual[['unique_id', 'ds', 'y']].rename(columns={'y': 'model'})
    predictions['model'] += 2
    ledger = match_point_predictions(actual, predictions.iloc[::-1], 'model')
    assert point_metrics(ledger)['mae_price'] == 2
    assert point_metrics(ledger)['persistence_mae_price'] == 8.5
    assert list(ledger.ds) == list(actual.ds)


def test_duplicate_predictions_and_nonfinite_values_are_rejected():
    _, actual = held_out_inputs(panel(), 'test')
    predictions = actual[['unique_id', 'ds', 'y']].rename(columns={'y': 'model'})
    duplicated = pd.concat([predictions.iloc[:-1], predictions.iloc[:1]])
    with pytest.raises(ValueError, match='keys or row count'):
        match_point_predictions(actual, duplicated, 'model')
    predictions.loc[0, 'model'] = np.inf
    with pytest.raises(ValueError, match='finite'):
        match_point_predictions(actual, predictions, 'model')


def test_context_gaps_insufficient_history_and_training_evaluation_are_rejected():
    frame = panel()
    frame.loc[20, 'ds'] += pd.Timedelta(minutes=1)
    with pytest.raises(ValueError, match='time gap'):
        held_out_inputs(frame, 'test')
    with pytest.raises(ValueError, match='insufficient context'):
        held_out_inputs(panel().iloc[1:], 'test')
    with pytest.raises(ValueError, match='held-out splits'):
        held_out_inputs(panel(), 'train')

"""Analytic scoring identities and training-only empirical baseline controls."""
import pytest

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")

from scripts.forecast_distribution_metrics import (  # noqa: E402
    fit_return_quantiles,
    float32_reference_errors,
    reconstructed_crps,
    weighted_interval_score,
)


def test_reference_comparison_preserves_float32_csv_precision_and_rejects_changes():
    model_value = np.array([[4322.029296875]], dtype=np.float32)
    np.testing.assert_array_equal(float32_reference_errors(model_value, [[4322.0293]]), [0.])
    assert float32_reference_errors(model_value, [[4322.0393]])[0] > .009


def test_point_mass_crps_and_wis_equal_absolute_error():
    y = np.array([-3., 0., 2.])
    pred = np.zeros((3, 5))
    q = [.01, .1, .5, .9, .99]
    np.testing.assert_allclose(reconstructed_crps(y, pred, q), np.abs(y))
    np.testing.assert_allclose(weighted_interval_score(y, pred, q), np.abs(y))


def test_uniform_crps_has_known_closed_form_including_outside_support():
    y = np.array([-.2, 0., .25, .5, 1., 1.2])
    pred = np.tile([0., .5, 1.], (len(y), 1))
    expected = [8/15, 1/3, 7/48, 1/12, 1/3, 8/15]
    np.testing.assert_allclose(reconstructed_crps(y, pred, [0., .5, 1.]), expected, atol=1e-12)


def test_clamped_quantile_tails_create_atoms_with_known_crps():
    # Q(.25)=0, Q(.75)=1 means 25% mass at either endpoint and 50% Uniform(0,1).
    np.testing.assert_allclose(reconstructed_crps([0., .5], [[0., 1.], [0., 1.]], [.25, .75]),
                               [13/48, 7/48], atol=1e-12)


def test_wis_matches_interval_formula_and_penalizes_excessive_width():
    # One 80% interval: width=4, observation exceeds upper by 1, IS=14.
    actual = weighted_interval_score([3.], [[-2., 0., 2.]], [.1, .5, .9])
    np.testing.assert_allclose(actual, [(0.5 * 3 + .1 * 14) / 1.5])
    assert weighted_interval_score([0.], [[-20., 0., 20.]], [.1, .5, .9])[0] > 0


def test_crps_and_wis_are_location_and_scale_equivariant():
    y = np.array([-.2, .3, 2.])
    pred = np.tile([0., .4, 1.], (3, 1))
    for score in (weighted_interval_score, reconstructed_crps):
        np.testing.assert_allclose(score(10 + 3*y, 10 + 3*pred, [.1, .5, .9]),
                                   3 * score(y, pred, [.1, .5, .9]), atol=1e-12)


@pytest.mark.parametrize("pred,q", [
    ([[1., 0., 2.]], [.1, .5, .9]),
    ([[0., float('nan'), 2.]], [.1, .5, .9]),
    ([[0., 1., 2.]], [.1, .1, .9]),
    ([[0., 1., 2.]], [-.1, .5, .9]),
])
def test_invalid_quantiles_are_rejected(pred, q):
    with pytest.raises(ValueError):
        reconstructed_crps([1.], pred, q)


def test_training_baseline_excludes_held_out_values_and_requires_training_only():
    frame = pd.DataFrame({'unique_id': ['a']*80 + ['b']*80,
                          'y': np.r_[np.arange(1, 81), np.arange(81, 161)],
                          'split': ['train']*80 + ['test']*80})
    original, count = fit_return_quantiles(frame.loc[frame.split.eq('train')], [.1, .5, .9])
    frame.loc[frame.split.eq('test'), 'y'] *= 10000
    repeated, other = fit_return_quantiles(frame.loc[frame.split.eq('train')], [.1, .5, .9])
    assert count == other == 1
    np.testing.assert_array_equal(original, repeated)
    np.testing.assert_allclose(original[:, 1], np.arange(1, 17) / 64)
    with pytest.raises(ValueError, match='training rows only'):
        fit_return_quantiles(frame, [.1, .5, .9])

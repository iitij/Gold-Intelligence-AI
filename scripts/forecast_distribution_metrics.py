"""Scores for a declared quantile grid and its bounded linear reconstruction."""
import numpy as np


def float32_reference_errors(predictions, reference):
    """Compare model float32 values to their shortest-decimal CSV round trips."""
    actual = np.asarray(predictions, dtype=np.float32)
    expected = np.asarray(reference, dtype=np.float32)
    if (actual.shape != expected.shape or actual.ndim != 2 or not actual.size
            or not np.isfinite(actual).all() or not np.isfinite(expected).all()):
        raise ValueError("Invalid float32 reference arrays")
    return np.abs(actual.astype(float) - expected.astype(float)).max(axis=0)


def validate_quantiles(outcomes, predictions, levels):
    y = np.asarray(outcomes, dtype=float)
    pred = np.asarray(predictions, dtype=float)
    q = np.asarray(levels, dtype=float)
    if (y.ndim != 1 or not len(y) or q.ndim != 1 or len(q) < 2
            or pred.shape != (len(y), len(q))):
        raise ValueError("Invalid outcome/quantile dimensions")
    if not (np.isfinite(y).all() and np.isfinite(pred).all() and np.isfinite(q).all()):
        raise ValueError("Scores require finite inputs")
    if q[0] < 0 or q[-1] > 1 or (np.diff(q) <= 0).any():
        raise ValueError("Quantile levels must strictly increase within [0, 1]")
    if (np.diff(pred, axis=1) < 0).any():
        raise ValueError("Quantile predictions must be monotone")
    return y, pred, q


def pinball_losses(outcomes, predictions, levels):
    y, pred, q = validate_quantiles(outcomes, predictions, levels)
    error = y[:, None] - pred
    return np.maximum(q * error, (q - 1) * error)


def weighted_interval_score(outcomes, predictions, levels):
    """WIS = twice mean pinball loss for paired quantiles plus one median."""
    q = np.asarray(levels, dtype=float)
    if (len(q) % 2 != 1 or not np.allclose(q + q[::-1], 1, atol=1e-12, rtol=0)
            or not np.isclose(q[len(q) // 2], .5, atol=1e-12, rtol=0)):
        raise ValueError("WIS requires a symmetric quantile grid with a median")
    return 2 * pinball_losses(outcomes, predictions, q).mean(axis=1)


def reconstructed_crps(outcomes, predictions, levels):
    """Exact CRPS of Q linear between supplied quantiles, constant beyond endpoints.

    This is not the unknown full model distribution's CRPS. Constant tails put
    atoms at the extreme reported values. Integration splits where Q equals y.
    """
    y, pred, q = validate_quantiles(outcomes, predictions, levels)
    if q[0] > 0:
        q = np.r_[0., q]
        pred = np.column_stack([pred[:, 0], pred])
    if q[-1] < 1:
        q = np.r_[q, 1.]
        pred = np.column_stack([pred, pred[:, -1]])
    result = np.zeros(len(y))
    for index, (lo, hi) in enumerate(zip(q[:-1], q[1:], strict=True)):
        width = hi - lo
        residual = y - pred[:, index]
        delta = pred[:, index + 1] - pred[:, index]
        crossing = np.divide(residual, delta, out=np.zeros(len(y)), where=delta > 0)
        crossing = np.where(delta == 0, (residual >= 0).astype(float), np.clip(crossing, 0, 1))

        def integral(a, b, coefficient):
            return width * (coefficient * residual * (b - a)
                            + (width * residual - coefficient * delta) * (b**2 - a**2) / 2
                            - width * delta * (b**3 - a**3) / 3)

        result += 2 * (integral(0, crossing, lo) + integral(crossing, 1, lo - 1))
    if not np.isfinite(result).all() or (result < -1e-10).any():
        raise ValueError("Invalid reconstructed CRPS")
    return np.maximum(result, 0)


def fit_return_quantiles(training, levels, *, context=64, horizon=16):
    """Fit only from supplied training segments; every origin has all outcomes."""
    if training.empty or not training.split.eq("train").all():
        raise ValueError("Baseline fit accepts training rows only")
    residuals = []
    for _, group in training.groupby("unique_id", sort=False):
        values = group.y.to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError("Training prices must be finite and positive")
        for origin in range(context - 1, len(values) - horizon):
            residuals.append(values[origin + 1:origin + horizon + 1] / values[origin] - 1)
    if not residuals:
        raise ValueError("No complete training forecast origins")
    return np.quantile(residuals, levels, axis=0).T, len(residuals)

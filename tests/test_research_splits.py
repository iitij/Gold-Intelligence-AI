"""Synthetic interval-boundary tests; not actual model evaluation."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from goldintel.research.point_in_time import PointInTimeError
from goldintel.research.splits import LabeledInterval, build_anchored_fold

UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def at(hour):
    return T0 + timedelta(hours=hour)


def sample(name, begin, end, *, known=None):
    return LabeledInterval(name, at(begin), at(end), at(end if known is None else known))


def fold(samples, *, train=24, test_start=26, test_end=36, embargo=0):
    return build_anchored_fold(
        samples, train_cutoff_at_utc=at(train), test_start_at_utc=at(test_start),
        test_end_at_utc=at(test_end), embargo=timedelta(hours=embargo),
    )


def test_only_historically_known_labels_selected():
    out = fold([sample("train", 10, 15), sample("test", 28, 29)])
    assert out.train_sample_ids == ("train",)
    assert out.test_sample_ids == ("test",)
    assert out.excluded_sample_ids == ()


def test_training_label_crossing_validation_start_is_purged():
    out = fold([sample("ok", 10, 15), sample("leak", 24, 27), sample("test", 28, 29)])
    assert out.train_sample_ids == ("ok",)
    assert out.excluded_sample_ids == ("leak",)


def test_training_label_not_yet_published_is_purged():
    out = fold([sample("ok", 10, 15), sample("late", 23, 24, known=27),
                sample("test", 28, 29)])
    assert out.excluded_sample_ids == ("late",)


def test_embargo_excludes_labels_near_boundary():
    out = fold([sample("ok", 10, 15), sample("close", 20, 24),
                sample("test", 28, 29)], embargo=3)
    assert out.train_sample_ids == ("ok",)
    assert "close" in out.excluded_sample_ids


def test_holdout_outcome_not_yet_known_is_excluded():
    out = fold([sample("ok", 10, 15), sample("valid", 28, 29),
                sample("late", 34, 38)])
    assert out.test_sample_ids == ("valid",)
    assert "late" in out.excluded_sample_ids


def test_gap_and_future_candidates_excluded():
    out = fold([sample("ok", 10, 15), sample("gap", 25, 26),
                sample("valid", 28, 29), sample("future", 40, 41)])
    assert set(out.excluded_sample_ids) == {"gap", "future"}


def test_deterministic_sorting_of_samples():
    out = fold([sample("test-z", 28, 30), sample("train-z", 15, 16),
                sample("train-a", 10, 11), sample("test-a", 27, 28)])
    assert out.train_sample_ids == ("train-a", "train-z")
    assert out.test_sample_ids == ("test-a", "test-z")


def test_duplicate_ids_are_rejected():
    with pytest.raises(PointInTimeError, match="Duplicate"):
        fold([sample("same", 10, 15), sample("same", 28, 29)])


def test_invalid_label_timestamps_rejected():
    with pytest.raises(PointInTimeError, match="inconsistent"):
        sample("bad", 20, 19)
    with pytest.raises(PointInTimeError, match="inconsistent"):
        sample("bad", 20, 22, known=21)


def test_utc_is_required():
    with pytest.raises(PointInTimeError, match="UTC"):
        replace(sample("ok", 10, 15), decision_at_utc=at(10).replace(tzinfo=None))


def test_empty_train_or_test_rejected():
    with pytest.raises(PointInTimeError, match="no fully observable"):
        fold([sample("train", 10, 15)])


@pytest.mark.parametrize("embargo", [-1, 100])
def test_negative_or_unsatisfiable_embargo_rejected(embargo):
    with pytest.raises(PointInTimeError, match="no fully observable|Negative"):
        fold([sample("train", 10, 15), sample("test", 28, 29)], embargo=embargo)


def test_training_cutoff_must_precede_testing():
    with pytest.raises(PointInTimeError, match="chronology"):
        fold([sample("train", 10, 15), sample("test", 28, 29)], train=26)


def test_test_end_is_exclusive():
    out = fold([sample("train", 10, 15), sample("test", 28, 29),
                sample("edge", 36, 37)])
    assert out.test_sample_ids == ("test",)
    assert "edge" in out.excluded_sample_ids

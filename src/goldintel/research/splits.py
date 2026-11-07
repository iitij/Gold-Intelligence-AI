"""Anchored, purged walk-forward interval selection for research samples.

No ML estimator, scaler, broker data or order-execution permissions.
A training outcome must be historically known before validation starts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from goldintel.research.point_in_time import PointInTimeError, _require_utc


@dataclass(frozen=True)
class LabeledInterval:
    sample_id: str
    decision_at_utc: datetime
    outcome_end_at_utc: datetime
    outcome_available_at_utc: datetime

    def __post_init__(self) -> None:
        if not self.sample_id.strip():
            raise PointInTimeError("Missing sample provenance")
        for name in ("decision_at_utc", "outcome_end_at_utc", "outcome_available_at_utc"):
            _require_utc(getattr(self, name), name)
        if not (self.decision_at_utc < self.outcome_end_at_utc <=
                self.outcome_available_at_utc):
            raise PointInTimeError("Label timing is inconsistent")


@dataclass(frozen=True)
class AnchoredFold:
    train_sample_ids: tuple[str, ...]
    test_sample_ids: tuple[str, ...]
    excluded_sample_ids: tuple[str, ...]
    train_cutoff_at_utc: datetime
    test_start_at_utc: datetime
    test_end_at_utc: datetime
    embargo: timedelta


def build_anchored_fold(
    samples: Sequence[LabeledInterval],
    *,
    train_cutoff_at_utc: datetime,
    test_start_at_utc: datetime,
    test_end_at_utc: datetime,
    embargo: timedelta = timedelta(0),
) -> AnchoredFold:
    """Select train/test intervals without overlapping future label information.

    Training decisions must be <= train_cutoff. Their outcomes must finish
    strictly before test_start - embargo and become available by test_start.
    Test decisions belong to [test_start, test_end); completed test labels
    must become available by test_end. This is an anchored forward-only split.
    """
    for name, dt in (("train_cutoff_at_utc", train_cutoff_at_utc),
                     ("test_start_at_utc", test_start_at_utc),
                     ("test_end_at_utc", test_end_at_utc)):
        _require_utc(dt, name)
    if not (train_cutoff_at_utc < test_start_at_utc < test_end_at_utc):
        raise PointInTimeError("Train/test chronology is invalid")
    if not isinstance(embargo, timedelta) or embargo < timedelta(0):
        raise PointInTimeError("Negative or invalid embargo")

    train: list[LabeledInterval] = []
    test: list[LabeledInterval] = []
    excluded: list[LabeledInterval] = []
    seen: set[str] = set()
    purge_before = test_start_at_utc - embargo
    for sample in samples:
        if sample.sample_id in seen:
            raise PointInTimeError("Duplicate sample id")
        seen.add(sample.sample_id)
        if sample.decision_at_utc <= train_cutoff_at_utc:
            if (sample.outcome_end_at_utc < purge_before and
                    sample.outcome_available_at_utc <= test_start_at_utc):
                train.append(sample)
            else:
                excluded.append(sample)
        elif test_start_at_utc <= sample.decision_at_utc < test_end_at_utc:
            if sample.outcome_available_at_utc <= test_end_at_utc:
                test.append(sample)
            else:
                excluded.append(sample)
        else:
            excluded.append(sample)
    train.sort(key=lambda x: (x.decision_at_utc, x.sample_id))
    test.sort(key=lambda x: (x.decision_at_utc, x.sample_id))
    excluded.sort(key=lambda x: (x.decision_at_utc, x.sample_id))
    if not train or not test:
        raise PointInTimeError("Fold has no fully observable train/test samples")
    return AnchoredFold(
        train_sample_ids=tuple(x.sample_id for x in train),
        test_sample_ids=tuple(x.sample_id for x in test),
        excluded_sample_ids=tuple(x.sample_id for x in excluded),
        train_cutoff_at_utc=train_cutoff_at_utc,
        test_start_at_utc=test_start_at_utc,
        test_end_at_utc=test_end_at_utc,
        embargo=embargo,
    )

"""Strict point-in-time feature construction for completed XAUUSD bars.

Never use future bars or data released after decision time.
Independent of ML models, brokers, and execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Sequence

FRAME_SECONDS = {"M15": 900, "H1": 3600, "H4": 14400}
MAX_STALENESS = {
    "M15": timedelta(minutes=45), "H1": timedelta(hours=3),
    "H4": timedelta(hours=12),
}


class PointInTimeError(ValueError):
    """A feature snapshot cannot be proven historically available."""


def _require_utc(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise PointInTimeError(f"{name} must be explicitly UTC")


def _positive_finite(number: Decimal, field: str) -> None:
    if not isinstance(number, Decimal) or not number.is_finite() or number <= 0:
        raise PointInTimeError(f"{field} must be a finite positive Decimal")


@dataclass(frozen=True)
class CompletedGoldBar:
    timeframe: str
    opened_at_utc: datetime
    closed_at_utc: datetime
    available_at_utc: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    source_id: str
    asset_id: str = "XAUUSD"

    def __post_init__(self) -> None:
        if self.asset_id != "XAUUSD" or self.timeframe not in FRAME_SECONDS:
            raise PointInTimeError("Unsupported instrument or timeframe")
        for name in ("opened_at_utc", "closed_at_utc", "available_at_utc"):
            _require_utc(getattr(self, name), name)
        if self.closed_at_utc - self.opened_at_utc != timedelta(
            seconds=FRAME_SECONDS[self.timeframe]
        ):
            raise PointInTimeError("Bar open/close does not match timeframe")
        if self.available_at_utc < self.closed_at_utc:
            raise PointInTimeError("Completed bar cannot be available before closing")
        if not self.source_id.strip():
            raise PointInTimeError("Missing bar source provenance")
        for name in ("open", "high", "low", "close"):
            _positive_finite(getattr(self, name), name)
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise PointInTimeError("Invalid OHLC values")


@dataclass(frozen=True)
class EconomicObservation:
    """Actual economic release/revision, never a scheduled future forecast."""

    series_id: str
    reference_at_utc: datetime
    available_at_utc: datetime
    value: Decimal
    source_id: str
    revision_id: str

    def __post_init__(self) -> None:
        _require_utc(self.reference_at_utc, "reference_at_utc")
        _require_utc(self.available_at_utc, "available_at_utc")
        if self.available_at_utc < self.reference_at_utc:
            raise PointInTimeError("Observation published before its reference")
        if not self.series_id.strip() or not self.source_id.strip() or not self.revision_id.strip():
            raise PointInTimeError("Missing economic observation provenance")
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise PointInTimeError("Invalid economic observation")


@dataclass(frozen=True)
class GoldFeatures:
    decision_at_utc: datetime
    values: tuple[tuple[str, Decimal], ...]
    evidence: tuple[tuple[str, str, str], ...]
    execution_ready: bool = False

    def as_dict(self) -> dict[str, Decimal]:
        return dict(self.values)


def latest_released_observations(
    observations: Sequence[EconomicObservation], decision_at_utc: datetime
) -> dict[str, EconomicObservation]:
    """Use the most recent historically available reference and revision."""
    _require_utc(decision_at_utc, "decision_at_utc")
    latest: dict[str, EconomicObservation] = {}
    seen: set[tuple[str, datetime, datetime]] = set()
    for item in observations:
        key = (item.series_id, item.reference_at_utc, item.available_at_utc)
        if key in seen:
            raise PointInTimeError("Duplicate economic observation revision")
        seen.add(key)
        if item.available_at_utc > decision_at_utc:
            continue
        previous = latest.get(item.series_id)
        if previous is None or (
            item.reference_at_utc, item.available_at_utc, item.revision_id
        ) > (previous.reference_at_utc, previous.available_at_utc, previous.revision_id):
            latest[item.series_id] = item
    return latest


def make_gold_features(
    bars: Sequence[CompletedGoldBar],
    decision_at_utc: datetime,
    *,
    required_timeframes: tuple[str, ...] = ("M15", "H1", "H4"),
) -> GoldFeatures:
    """Compute research-only lagged features from closed, released bars.

    No tick/spread/broker session/macro inference; this is NOT a
    training-ready dataset or an executable trading decision.
    """
    _require_utc(decision_at_utc, "decision_at_utc")
    if not required_timeframes or "M15" not in required_timeframes:
        raise PointInTimeError("M15 is required")
    if len(set(required_timeframes)) != len(required_timeframes):
        raise PointInTimeError("Duplicate requested timeframe")
    if any(tf not in FRAME_SECONDS for tf in required_timeframes):
        raise PointInTimeError("Unsupported requested timeframe")
    grouped: dict[str, list[CompletedGoldBar]] = {tf: [] for tf in required_timeframes}
    seen: set[tuple[str, datetime]] = set()
    for bar in bars:
        key = (bar.timeframe, bar.closed_at_utc)
        if key in seen:
            raise PointInTimeError("Duplicate bar at timeframe and close")
        seen.add(key)
        if bar.timeframe in grouped and (
            bar.closed_at_utc <= decision_at_utc
            and bar.available_at_utc <= decision_at_utc
        ):
            grouped[bar.timeframe].append(bar)
    selected: dict[str, CompletedGoldBar] = {}
    for tf in required_timeframes:
        history = sorted(grouped[tf], key=lambda b: b.closed_at_utc)
        if not history:
            raise PointInTimeError(f"No historically available {tf} bar")
        selected[tf] = history[-1]
        if decision_at_utc - selected[tf].closed_at_utc > MAX_STALENESS[tf]:
            raise PointInTimeError(f"Stale {tf} bar for this decision")
        grouped[tf] = history
    m15 = grouped["M15"]
    if len(m15) < 2:
        raise PointInTimeError("At least two historically available M15 bars required")
    current, previous = m15[-1], m15[-2]
    if current.closed_at_utc - previous.closed_at_utc != timedelta(minutes=15):
        raise PointInTimeError("Nonconsecutive M15 history")
    fields = [
        ("m15_return_1", current.close / previous.close - Decimal(1)),
        ("m15_range_fraction", (current.high - current.low) / current.close),
        ("m15_body_fraction", (current.close - current.open) / current.close),
    ]
    for tf in required_timeframes:
        fields.append((f"{tf.lower()}_last_close", selected[tf].close))
    evidence = tuple(
        (tf, selected[tf].source_id, selected[tf].available_at_utc.isoformat())
        for tf in required_timeframes
    )
    return GoldFeatures(decision_at_utc, tuple(fields), evidence)

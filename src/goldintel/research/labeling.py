"""Research-only OHLC triple-barrier labels with ambiguity rejection.

Not executable P&L. OHLC candles cannot determine order of stop/target
touches or guarantee Bid/Ask fills. Never include labels in inference inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Sequence

from goldintel.research.point_in_time import (
    CompletedGoldBar,
    PointInTimeError,
    _positive_finite,
    _require_utc,
)


class BarrierOutcome(str, Enum):
    TARGET = "TARGET"
    STOP = "STOP"
    TIMEOUT = "TIMEOUT"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class BarrierLabel:
    outcome: BarrierOutcome
    observed_until_utc: datetime
    reason: str
    executable_pnl_verified: bool = False


def hypothetical_barrier_label(
    *,
    side: str,
    decision_at_utc: datetime,
    entry: Decimal,
    stop: Decimal,
    target: Decimal,
    future_m15_bars: Sequence[CompletedGoldBar],
    horizon_bars: int,
) -> BarrierLabel:
    """Label hypothetical barriers only with consecutive future M15 OHLC bars.

    The first future bar must OPEN at decision time; price gaps or both
    targets in one bar are AMBIGUOUS, never assumed profitable.
    """
    _require_utc(decision_at_utc, "decision_at_utc")
    if side not in ("BUY", "SELL"):
        raise PointInTimeError("Only BUY or SELL hypotheses may be labeled")
    if not isinstance(horizon_bars, int) or isinstance(horizon_bars, bool) or horizon_bars < 1:
        raise PointInTimeError("Invalid positive horizon")
    for field, value in (("entry", entry), ("stop", stop), ("target", target)):
        _positive_finite(value, field)
    if (side == "BUY" and not stop < entry < target) or (
        side == "SELL" and not target < entry < stop
    ):
        raise PointInTimeError("Stop/target on the wrong side of entry")
    if len(future_m15_bars) < horizon_bars:
        raise PointInTimeError("Insufficient future bars to prove timeout")
    for i, bar in enumerate(future_m15_bars[:horizon_bars]):
        if bar.timeframe != "M15":
            raise PointInTimeError("Only M15 OHLC labels supported")
        expected = decision_at_utc + i * timedelta(minutes=15)
        if bar.opened_at_utc != expected:
            raise PointInTimeError("Missing or misaligned future M15 bar")
        if not min(stop, target) < bar.open < max(stop, target):
            return BarrierLabel(BarrierOutcome.AMBIGUOUS, bar.closed_at_utc,
                                "open_price_crosses_a_barrier")
        target_hit = bar.high >= target if side == "BUY" else bar.low <= target
        stop_hit = bar.low <= stop if side == "BUY" else bar.high >= stop
        if target_hit and stop_hit:
            return BarrierLabel(BarrierOutcome.AMBIGUOUS, bar.closed_at_utc,
                                "intrabar_order_unknown")
        if stop_hit:
            return BarrierLabel(BarrierOutcome.STOP, bar.closed_at_utc, "stop_touched")
        if target_hit:
            return BarrierLabel(BarrierOutcome.TARGET, bar.closed_at_utc, "target_touched")
    return BarrierLabel(
        BarrierOutcome.TIMEOUT, future_m15_bars[horizon_bars - 1].closed_at_utc,
        "horizon_expired"
    )

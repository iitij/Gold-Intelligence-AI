"""Observed-quote exit simulation for one-ounce research positions."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterable

from goldintel.research.point_in_time import PointInTimeError, _require_utc


@dataclass(frozen=True)
class ExitResult:
    reason: str
    time: datetime | None
    price: Decimal | None
    gross_usd_per_ounce: Decimal | None


def simulate_exit(
    quotes: Iterable[tuple[datetime, Decimal, Decimal]],
    *,
    side: str,
    entry_time: datetime,
    entry_price: Decimal,
    deadline: datetime,
    stop_distance: Decimal | None,
    target_distance: Decimal | None,
    max_gap: timedelta,
) -> ExitResult:
    """Fill on observed liquidation prices, with unknown fills across long gaps."""
    _require_utc(entry_time, "entry_time")
    _require_utc(deadline, "deadline")
    if side not in ("long", "short") or deadline <= entry_time or max_gap <= timedelta(0):
        raise PointInTimeError("Invalid exit configuration")
    for value in (entry_price, *(v for v in (stop_distance, target_distance) if v is not None)):
        if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
            raise PointInTimeError("Exit prices and distances must be positive Decimals")
    previous = entry_time
    sign = Decimal(1) if side == "long" else Decimal(-1)
    for time, bid, ask in quotes:
        _require_utc(time, "quote time")
        if time < previous:
            raise PointInTimeError("Exit quotes must be chronological and follow entry")
        if not all(isinstance(p, Decimal) and p.is_finite() for p in (bid, ask)) or not 0 < bid <= ask:
            raise PointInTimeError("Invalid exit Bid/Ask")
        if time - previous > max_gap:
            return ExitResult("unknown_gap", None, None, None)
        previous = time
        price = bid if side == "long" else ask
        gross = sign * (price - entry_price)
        reason = None
        if time >= deadline:
            reason = "deadline"
        elif stop_distance is not None and gross <= -stop_distance:
            reason = "stop"
        elif target_distance is not None and gross >= target_distance:
            reason = "target"
        if reason is not None:
            return ExitResult(reason, time, price, gross)
    return ExitResult("unknown_missing_exit", None, None, None)

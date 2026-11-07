"""Research-only synthetic OHLC barrier tests; never executable P&L."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from goldintel.research.labeling import BarrierOutcome, hypothetical_barrier_label
from goldintel.research.point_in_time import CompletedGoldBar, PointInTimeError

START = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)


def bar(index, *, op="2000", hi="2002", lo="1998", cl="2001"):
    start = START + index * timedelta(minutes=15)
    end = start + timedelta(minutes=15)
    return CompletedGoldBar("M15", start, end, end, D(op), D(hi), D(lo), D(cl), "synthetic")


def label(side="BUY", bars=None, horizon=1):
    return hypothetical_barrier_label(
        side=side, decision_at_utc=START, entry=D("2000"),
        stop=D("1997") if side == "BUY" else D("2003"),
        target=D("2003") if side == "BUY" else D("1997"),
        future_m15_bars=bars or [bar(0)], horizon_bars=horizon,
    )


def test_buy_target_touched():
    result = label(bars=[bar(0, hi="2004")])
    assert result.outcome == BarrierOutcome.TARGET
    assert not result.executable_pnl_verified


def test_sell_stop_touched():
    assert label(side="SELL", bars=[bar(0, hi="2004")]).outcome == BarrierOutcome.STOP


def test_sell_target_touched():
    assert label(side="SELL", bars=[bar(0, lo="1996")]).outcome == BarrierOutcome.TARGET


def test_buy_stop_touched():
    assert label(bars=[bar(0, lo="1996")]).outcome == BarrierOutcome.STOP


def test_both_barriers_same_bar_are_ambiguous():
    result = label(bars=[bar(0, hi="2004", lo="1996")])
    assert result.outcome == BarrierOutcome.AMBIGUOUS
    assert result.reason == "intrabar_order_unknown"


def test_gap_beyond_target_cannot_be_counted_as_profit():
    result = label(bars=[bar(0, op="2004", hi="2005", lo="1999", cl="2004")])
    assert result.outcome == BarrierOutcome.AMBIGUOUS


def test_timeout_after_full_horizon():
    result = label(bars=[bar(0), bar(1)], horizon=2)
    assert result.outcome == BarrierOutcome.TIMEOUT
    assert result.observed_until_utc == START + timedelta(minutes=30)


def test_insufficient_horizon_rejected():
    with pytest.raises(PointInTimeError, match="Insufficient"):
        label(bars=[bar(0)], horizon=2)


def test_gap_in_future_bars_rejected():
    with pytest.raises(PointInTimeError, match="misaligned"):
        label(bars=[bar(0), bar(2)], horizon=2)


def test_no_trade_not_a_trade_label():
    with pytest.raises(PointInTimeError, match="BUY or SELL"):
        label(side="NO_TRADE")


def test_wrong_stop_direction_rejected():
    with pytest.raises(PointInTimeError, match="wrong side"):
        hypothetical_barrier_label(
            side="BUY", decision_at_utc=START, entry=D("2000"),
            stop=D("2001"), target=D("2003"), future_m15_bars=[bar(0)],
            horizon_bars=1,
        )


def test_non_m15_label_bar_rejected():
    bad = replace(bar(0), timeframe="H1",
                  closed_at_utc=START + timedelta(hours=1),
                  available_at_utc=START + timedelta(hours=1))
    with pytest.raises(PointInTimeError, match="Only M15"):
        label(bars=[bad])

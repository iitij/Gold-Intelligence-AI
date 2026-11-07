"""Synthetic point-in-time tests. No broker, real data or trained models."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from goldintel.research.point_in_time import (
    CompletedGoldBar,
    EconomicObservation,
    PointInTimeError,
    latest_released_observations,
    make_gold_features,
)

UTC = timezone.utc
START = datetime(2026, 11, 6, 12, tzinfo=UTC)


def bar(tf, minutes_ago, *, open_="2000", high="2005", low="1995", close="2001",
        available_lag=0, source="broker"):
    durations = {"M15": 15, "H1": 60, "H4": 240}
    end = START - timedelta(minutes=minutes_ago)
    return CompletedGoldBar(
        timeframe=tf, opened_at_utc=end - timedelta(minutes=durations[tf]),
        closed_at_utc=end, available_at_utc=end + timedelta(seconds=available_lag),
        open=D(open_), high=D(high), low=D(low), close=D(close), source_id=source,
    )


def history():
    return [bar("M15", 15, close="2000"), bar("M15", 0), bar("H1", 0), bar("H4", 0)]


def test_features_use_only_closed_released_bars():
    snap = make_gold_features(history(), START)
    assert snap.as_dict()["m15_return_1"] == D("0.0005")
    assert snap.as_dict()["m15_last_close"] == D("2001")
    assert not snap.execution_ready
    assert len(snap.evidence) == 3


def test_future_candles_cannot_leak_into_features():
    h = history()
    future = replace(
        h[1], opened_at_utc=START, closed_at_utc=START + timedelta(minutes=15),
        available_at_utc=START + timedelta(minutes=15), close=D("2010"), high=D("2015"),
    )
    snap = make_gold_features(h + [future], START)
    assert snap.as_dict()["m15_last_close"] == D("2001")


def test_late_availability_excludes_completed_bar():
    h = history()
    h[1] = replace(h[1], available_at_utc=START + timedelta(seconds=1))
    h.insert(0, bar("M15", 30, close="1999"))
    snap = make_gold_features(h, START)
    assert snap.as_dict()["m15_last_close"] == D("2000")


def test_h1_not_used_before_close_even_if_present_in_dataset():
    h = history()
    h.append(replace(bar("H1", -60, close="2005"),
                     available_at_utc=START + timedelta(hours=1)))
    snap = make_gold_features(h, START)
    assert snap.as_dict()["h1_last_close"] == D("2001")


def test_missing_completed_h4_rejected():
    with pytest.raises(PointInTimeError, match="H4"):
        make_gold_features(history()[:-1], START)


def test_stale_session_fails_closed():
    with pytest.raises(PointInTimeError, match="Stale"):
        make_gold_features(history(), START + timedelta(days=3))


def test_nonconsecutive_m15_rejected():
    h = history()
    h[0] = bar("M15", 30, close="2000")
    with pytest.raises(PointInTimeError, match="Nonconsecutive"):
        make_gold_features(h, START)


def test_duplicate_market_bar_rejected_even_if_future():
    h = history()
    with pytest.raises(PointInTimeError, match="Duplicate bar"):
        make_gold_features(h + [h[0]], START)


def test_no_utc_inference_from_naive_or_non_utc_times():
    h = history()
    with pytest.raises(PointInTimeError, match="UTC"):
        make_gold_features(h, START.replace(tzinfo=None))
    with pytest.raises(PointInTimeError, match="UTC"):
        make_gold_features(h, START.astimezone(timezone(timedelta(hours=3))))


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "0", "-1"])
def test_bad_prices_are_rejected(bad):
    with pytest.raises(PointInTimeError):
        bar("M15", 0, close=bad)


def test_invalid_ohlc_geometry_rejected():
    with pytest.raises(PointInTimeError):
        bar("M15", 0, high="1999")


def test_bar_unavailable_before_close():
    with pytest.raises(PointInTimeError, match="before closing"):
        bar("M15", 0, available_lag=-1)


def test_cot_release_timing_and_future_revision_are_not_leaked():
    reference = START - timedelta(days=3)
    first = EconomicObservation("CFTC_GOLD", reference, START, D("1200"), "cftc", "v1")
    revision = EconomicObservation("CFTC_GOLD", reference, START + timedelta(days=5),
                                   D("9999"), "cftc", "v2")
    before = latest_released_observations([first, revision],
                                          START - timedelta(seconds=1))
    assert "CFTC_GOLD" not in before
    assert latest_released_observations([first, revision], START)["CFTC_GOLD"].value == D("1200")
    later = latest_released_observations([first, revision], START + timedelta(days=6))
    assert later["CFTC_GOLD"].value == D("9999")


def test_duplicate_economic_revision_rejected():
    obs = EconomicObservation("US_CPI", START, START, D("0.1"), "cpi", "v1")
    with pytest.raises(PointInTimeError, match="Duplicate"):
        latest_released_observations([obs, obs], START)


def test_conflicting_revisions_at_identical_publication_time_fail_closed():
    a = EconomicObservation("US_CPI", START, START, D("0.1"), "cpi", "v1")
    b = EconomicObservation("US_CPI", START, START, D("0.2"), "cpi", "v2")
    with pytest.raises(PointInTimeError, match="Duplicate"):
        latest_released_observations([a, b], START)

"""Catch seasonal conversion errors and unfair cohorts across clock hypotheses."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from scripts.compare_bls_clock_anchors import event_result, parse_release


def test_eastern_embargo_uses_us_dst_while_hypotheses_remain_independent():
    zone = ZoneInfo("America/New_York")
    before = parse_release({"release_local": "2026-03-06T08:30:00"}, zone)
    after = parse_release({"release_local": "2026-03-11T08:30:00"}, zone)
    assert before.isoformat() == "2026-03-06T13:30:00+00:00"
    assert after.isoformat() == "2026-03-11T12:30:00+00:00"


def test_both_feeds_drop_the_same_missing_control_and_keep_winner():
    event = datetime(2026, 7, 2, 12, 30, tzinfo=timezone.utc)
    native_zero = event.replace(tzinfo=None)
    offsets = [60, 120, 180, 240]
    controls = [-21, -14, -7, 7, 14, 21]
    bars = {native_zero + timedelta(days=d, minutes=m): Decimal(1)
            for d in [0, *controls] for m in offsets}
    bars[native_zero + timedelta(minutes=180)] = Decimal(4)
    second = bars.copy()
    missing = native_zero + timedelta(days=-7, minutes=60)
    del second[missing]
    other_news = (event + timedelta(days=14)).date()
    out = event_result(event, {"a": bars, "b": second}, offsets, controls, {other_news}, 3)
    assert out["status"] == "compared"
    assert out["excluded_controls"][str(missing.date())] == "missing_common_control_bars"
    assert out["excluded_controls"][str(other_news)] == "another_registered_release"
    assert len(out["common_controls"]) == 4
    for feed in out["feeds"].values():
        assert feed["largest_range_multiple_offsets"] == [180]
        assert all(len(case["matched_weekday_control_ranges_bps"]) == 4 for case in feed["cases"])
    del second[native_zero + timedelta(minutes=120)]
    out = event_result(event, {"a": bars, "b": second}, offsets, controls, {other_news}, 3)
    assert out["status"] == "missing_common_event_bars"
    assert out["feeds"] == {}

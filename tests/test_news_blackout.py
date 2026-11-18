from datetime import datetime, timedelta, timezone

from goldintel.research.news_blackout import CalendarVersion, blackout_events


def stamp(day, hour=0):
    return datetime(2025, 12, day, hour, tzinfo=timezone.utc)


def test_schedule_revision_only_applies_after_publication():
    versions = [
        CalendarVersion("jobs", stamp(1), stamp(5, 13), False, "original"),
        CalendarVersion("jobs", stamp(6), stamp(16, 13), False, "revision"),
    ]
    window = timedelta(minutes=30)
    assert blackout_events(versions, stamp(5, 13), window, window) == ("jobs",)
    assert blackout_events(versions, stamp(16, 13), window, window) == ("jobs",)
    assert blackout_events(versions, stamp(7, 13), window, window) == ()


def test_cancellation_and_unknown_future_schedule():
    versions = [
        CalendarVersion("jobs", stamp(1), stamp(5, 13), False, "original"),
        CalendarVersion("jobs", stamp(4), stamp(5, 13), True, "cancellation"),
        CalendarVersion("cpi", stamp(6), stamp(5, 13), False, "late evidence"),
    ]
    assert blackout_events(versions, stamp(5, 13), timedelta(hours=1), timedelta(hours=1)) == ()


def test_conflicting_versions_rejected_regardless_of_input_order():
    import itertools

    import pytest

    from goldintel.research.point_in_time import PointInTimeError

    rows = [
        CalendarVersion("jobs", stamp(1), stamp(5, 13), False, "source-a"),
        CalendarVersion("jobs", stamp(1), stamp(6, 13), False, "source-b"),
        CalendarVersion("jobs", stamp(3), stamp(7, 13), False, "newer"),
    ]
    for ordering in itertools.permutations(rows):
        with pytest.raises(PointInTimeError, match="Conflicting"):
            blackout_events(ordering, stamp(5), timedelta(hours=1), timedelta(hours=1))


def test_blackout_window_boundaries_are_inclusive():
    event = CalendarVersion("jobs", stamp(1), stamp(5, 13), False, "source")
    before = timedelta(minutes=30)
    after = timedelta(minutes=15)
    for time in (stamp(5, 13) - before, stamp(5, 13) + after):
        assert blackout_events([event], time, before, after) == ("jobs",)
    assert blackout_events(
        [event], stamp(5, 13) + after + timedelta(microseconds=1), before, after
    ) == ()

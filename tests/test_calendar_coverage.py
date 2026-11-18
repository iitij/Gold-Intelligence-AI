"""Calendar clearance needs current evidence covering every required event family."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from goldintel.research.calendar_coverage import (
    REQUIRED_FAMILIES,
    CalendarCoverage,
    assess_calendar,
)
from goldintel.research.news_blackout import CalendarVersion
from goldintel.research.point_in_time import PointInTimeError

T = datetime(2026, 11, 18, 19, 0, tzinfo=timezone.utc)
WINDOW = timedelta(minutes=30)


def coverage():
    return [CalendarCoverage(family, family, T - timedelta(minutes=1), T - timedelta(hours=2),
                             T + timedelta(hours=2), T + timedelta(hours=1), True)
            for family in REQUIRED_FAMILIES]


def assess(sources, versions=(), when=T):
    return assess_calendar(versions, sources, when, before=WINDOW, after=WINDOW)


def test_empty_verified_schedule_and_missing_future_evidence_have_different_meanings():
    sources = coverage()
    assert assess(sources)["status"] == "clear"
    sources[0] = replace(sources[0], known_at_utc=T + timedelta(seconds=1))
    out = assess(sources)
    assert out["status"] == "unknown"
    assert out["family_status"]["us_cpi"] == "missing"
    assert not out["calendar_coverage_verified"]
    assert not out["execution_ready"]


def test_latest_incomplete_evidence_overrides_prior_and_stale_evidence_expires():
    sources = coverage()
    incomplete = replace(sources[0], known_at_utc=T, complete=False)
    assert assess([*sources, incomplete])["family_status"]["us_cpi"] == "incomplete"
    assert assess(sources, when=T + timedelta(hours=1, seconds=1))["family_status"]["us_cpi"] == "stale"
    conflicting = replace(sources[0], source_id="other")
    with pytest.raises(PointInTimeError, match="Conflicting calendar coverage"):
        assess([*sources, conflicting])


def test_known_blackout_blocks_even_when_other_sources_missing_and_cancellation_is_causal():
    event = CalendarVersion("minutes", T - WINDOW, T, False, "fed")
    canceled = replace(event, known_at_utc=T + timedelta(minutes=1), canceled=True)
    initial = assess([], [event, canceled])
    assert initial["status"] == "scheduled_blackout"
    assert not initial["calendar_coverage_verified"]
    assert initial["known_blackout_events"] == ["minutes"]
    revised = assess(coverage(), [event, canceled], when=canceled.known_at_utc)
    assert revised["status"] == "clear"
    assert revised["known_blackout_events"] == []


def test_complete_receipt_must_cover_entire_candidate_event_window():
    sources = coverage()
    sources[0] = replace(sources[0], ends_before_utc=T + WINDOW)
    assert assess(sources)["family_status"]["us_cpi"] == "insufficient_window"

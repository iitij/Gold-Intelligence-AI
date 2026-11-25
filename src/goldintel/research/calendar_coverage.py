"""Require observed, current schedule coverage before treating a blackout check as clear."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from goldintel.research.news_blackout import CalendarVersion, blackout_events
from goldintel.research.point_in_time import PointInTimeError, _require_utc

REQUIRED_FAMILIES = ("us_cpi", "us_employment", "fomc_decision", "fomc_minutes")


@dataclass(frozen=True)
class CalendarCoverage:
    family: str
    source_id: str
    known_at_utc: datetime
    starts_at_utc: datetime
    ends_before_utc: datetime
    expires_at_utc: datetime
    complete: bool

    def __post_init__(self):
        for label in ("known_at_utc", "starts_at_utc", "ends_before_utc", "expires_at_utc"):
            _require_utc(getattr(self, label), label)
        if (self.family not in REQUIRED_FAMILIES or not self.source_id.strip()
                or self.starts_at_utc >= self.ends_before_utc or self.known_at_utc > self.expires_at_utc
                or type(self.complete) is not bool):
            raise PointInTimeError("Invalid calendar coverage interval")


def assess_calendar(
    versions: list[CalendarVersion],
    coverage: list[CalendarCoverage],
    decision_at_utc: datetime,
    *,
    before: timedelta,
    after: timedelta,
) -> dict:
    """Return scheduled blackout state and independent completeness for the event horizon."""
    active = blackout_events(versions, decision_at_utc, before, after)
    earliest = decision_at_utc - after
    latest = decision_at_utc + before
    newest = {}
    seen = {}
    for source in coverage:
        if source.known_at_utc > decision_at_utc:
            continue
        key = (source.family, source.known_at_utc)
        if key in seen and seen[key] != source:
            raise PointInTimeError("Conflicting calendar coverage versions")
        seen[key] = source
        previous = newest.get(source.family)
        if previous is None or previous.known_at_utc < source.known_at_utc:
            newest[source.family] = source
    status = {}
    for family in REQUIRED_FAMILIES:
        source = newest.get(family)
        if source is None:
            status[family] = "missing"
        elif not source.complete:
            status[family] = "incomplete"
        elif source.expires_at_utc < decision_at_utc:
            status[family] = "stale"
        elif not source.starts_at_utc <= earliest <= latest < source.ends_before_utc:
            status[family] = "insufficient_window"
        else:
            status[family] = "covered"
    complete = all(value == "covered" for value in status.values())
    return {
        "decision_at_utc": decision_at_utc.isoformat(),
        "event_search_start_utc": earliest.isoformat(),
        "event_search_end_utc": latest.isoformat(),
        "calendar_coverage_verified": complete,
        "family_status": status,
        "coverage_sources": {family: source.source_id for family, source in sorted(newest.items())},
        "known_blackout_events": list(active),
        "status": "scheduled_blackout" if active else ("clear" if complete else "unknown"),
        "execution_ready": False,
    }

"""Point-in-time economic-calendar blackout decisions."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from goldintel.research.point_in_time import PointInTimeError, _require_utc


@dataclass(frozen=True)
class CalendarVersion:
    event_id: str
    known_at_utc: datetime
    scheduled_at_utc: datetime
    canceled: bool
    source_id: str

    def __post_init__(self):
        _require_utc(self.known_at_utc, "known_at_utc")
        _require_utc(self.scheduled_at_utc, "scheduled_at_utc")
        if not self.event_id.strip() or not self.source_id.strip():
            raise PointInTimeError("Calendar event requires identity and source")
        if not isinstance(self.canceled, bool):
            raise PointInTimeError("Cancellation must be boolean")


def blackout_events(versions, decision_at_utc, before, after):
    """Return events whose latest known schedule covers the decision time."""
    _require_utc(decision_at_utc, "decision_at_utc")
    if before < timedelta(0) or after < timedelta(0):
        raise PointInTimeError("Blackout durations must be nonnegative")
    latest = {}
    seen = {}
    for version in versions:
        if version.known_at_utc > decision_at_utc:
            continue
        key = (version.event_id, version.known_at_utc)
        if key in seen and seen[key] != version:
            raise PointInTimeError("Conflicting calendar versions at the same time")
        seen[key] = version
        previous = latest.get(version.event_id)
        if previous is None or version.known_at_utc > previous.known_at_utc:
            latest[version.event_id] = version
    return tuple(sorted(
        version.event_id for version in latest.values()
        if not version.canceled
        and version.scheduled_at_utc - before <= decision_at_utc
        <= version.scheduled_at_utc + after
    ))

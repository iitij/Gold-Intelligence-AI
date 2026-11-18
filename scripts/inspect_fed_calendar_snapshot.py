"""Build a partial official calendar attachment for a captured XAUUSD snapshot."""

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from zoneinfo import ZoneInfo

from goldintel.data.snapshot import load_market_snapshot
from goldintel.research.calendar_coverage import CalendarCoverage, assess_calendar
from goldintel.research.news_blackout import CalendarVersion
from goldintel.research.point_in_time import _require_utc

FED = "https://www.federalreserve.gov"
EASTERN = ZoneInfo("America/New_York")
MONTHS = ("January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_observation(root, label, expected_url):
    response = (root / f"{label}.http").read_text().strip()
    if response != f"200 {expected_url}":
        raise ValueError("No successful response from the expected official URL")
    start, finish = (datetime.fromisoformat((root / f"{label}.{part}").read_text().strip())
                     for part in ("before", "after"))
    _require_utc(start, "request start")
    _require_utc(finish, "request completion")
    if not timedelta(0) <= finish - start <= timedelta(seconds=20):
        raise ValueError("Invalid official retrieval timing")
    raw = (root / f"{label}.html").read_bytes()
    if not 0 < len(raw) <= 2_000_000:
        raise ValueError("Invalid official response body size")
    return raw.decode("utf-8"), {
        "url": expected_url, "sha256": sha(raw), "request_started_at_utc": start.isoformat(),
        "observed_at_utc": finish.isoformat(),
    }


def text(html):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def eastern_time(year, month, day, hour, minute, suffix):
    if not 1 <= int(hour) <= 12:
        raise ValueError("Unexpected 12-hour clock")
    hour24 = int(hour) % 12 + (12 if suffix == "p.m." else 0)
    stamp = datetime(year, month, int(day), hour24, int(minute), tzinfo=EASTERN)
    return stamp.astimezone(timezone.utc)


def minutes_schedule(month_page, annual, year, month):
    month_name = MONTHS[month - 1]
    if f"<title>Federal Reserve Board - Calendar: {month_name} {year}" not in month_page:
        raise ValueError("Wrong Fed monthly calendar")
    # Read only the FOMC section, up to the next calendar section heading.
    pattern = r"<h4[^>]*>\s*FOMC Meetings\s*</h4>(.*?)<h4"
    blocks = re.findall(pattern, month_page, flags=re.DOTALL)
    if len(blocks) != 1:
        raise ValueError("Unexpected Fed calendar layout")
    section = text(blocks[0])
    result = re.fullmatch(
        r"Time: Release Date\(s\): (\d{1,2}):(\d{2}) ([ap]\.m\.) "
        r"FOMC Minutes Meeting of ([A-Za-z]+ \d{1,2}-\d{1,2}) (\d{1,2})", section,
    )
    if result is None:
        raise ValueError("Cannot attest coverage: an unsupported FOMC schedule section")
    hour, minute, suffix, meeting, day = result.groups()
    start = datetime(year, month, 1, tzinfo=EASTERN)
    end = datetime(year + (month == 12), (month % 12) + 1, 1, tzinfo=EASTERN)
    annual_matches = re.findall(rf"{year} FOMC Meetings</a>(.*?){year-1} FOMC Meetings</a>",
                                annual, flags=re.DOTALL)
    if len(annual_matches) != 1:
        raise ValueError("Missing Fed annual FOMC calendar section")
    meeting_months = re.findall(r'class="[^"]*\bfomc-meeting__month\b[^"]*">\s*'
                                r'<strong>([A-Za-z]+)</strong>', annual_matches[0])
    if (len(meeting_months) != 8 or month_name in meeting_months
            or f"Released {month_name} {int(day)}, {year}" not in annual_matches[0]):
        raise ValueError("Annual evidence does not corroborate the minutes-only month")
    return meeting, eastern_time(year, month, day, hour, minute, suffix), start, end


def verify_release(page, meeting, scheduled):
    local = scheduled.astimezone(EASTERN)
    date_label = f"{MONTHS[local.month-1]} {local.day}, {local.year}"
    release_time = f"{local.hour % 12 or 12}:{local.minute:02d} {'p.m.' if local.hour >= 12 else 'a.m.'}"
    if (f'<p class="article__time">{date_label}</p>' not in page
            or f"Minutes of the Federal Open Market Committee, {meeting}, {local.year}" not in page
            or f'For release at {release_time} {local.tzname()}' not in page):
        raise ValueError("Fed embargo release does not corroborate the schedule")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    snapshot = load_market_snapshot(args.snapshot, args.snapshot_id)
    decision = datetime.fromisoformat(snapshot.as_dict()["decision_at_utc"])
    local = decision.astimezone(EASTERN)
    year, month = local.year, local.month
    if any((args.sources / f"ntp-{part}.txt").read_text().strip() != "NTPSynchronized=yes"
           for part in ("before", "after")):
        raise ValueError("Official calendar acquisition lacks host clock synchronization evidence")
    monthly, monthly_source = read_observation(
        args.sources, "fed-month", f"{FED}/newsevents/{year}-{MONTHS[month-1]}.htm",
    )
    annual, annual_source = read_observation(args.sources, "fed", f"{FED}/monetarypolicy/fomccalendars.htm")
    meeting, scheduled, first, last = minutes_schedule(monthly, annual, year, month)
    local_release = scheduled.astimezone(EASTERN)
    schedule_observed = max(datetime.fromisoformat(row["observed_at_utc"])
                            for row in (monthly_source, annual_source))
    sources = {"monthly": monthly_source, "annual": annual_source}
    source_id = "fed-fomc-" + sha(json.dumps(sources, sort_keys=True).encode())
    observed = None
    if (args.sources / "fed-release.html").is_file():
        release, release_source = read_observation(
            args.sources, "fed-release",
            f"{FED}/newsevents/pressreleases/monetary{local_release:%Y%m%d}a.htm",
        )
        release_fetch_at = datetime.fromisoformat(release_source["observed_at_utc"])
        if release_fetch_at <= decision:
            verify_release(release, meeting, scheduled)
            if release_fetch_at < scheduled:
                raise ValueError("Release evidence precedes official publication boundary")
            observed = release_fetch_at
            sources["release"] = release_source
    event = CalendarVersion(f"fomc-minutes-{scheduled.date()}", schedule_observed, scheduled, False, source_id)
    coverage = [CalendarCoverage(family, source_id, schedule_observed, first.astimezone(timezone.utc),
                                 last.astimezone(timezone.utc), schedule_observed + timedelta(hours=1), True)
                for family in ("fomc_decision", "fomc_minutes")]
    policy = {"before_minutes": 30, "after_minutes": 30}
    kwargs = {"before": timedelta(minutes=policy["before_minutes"]),
              "after": timedelta(minutes=policy["after_minutes"])}
    state = assess_calendar([event], coverage, decision, **kwargs)
    current = datetime.now(timezone.utc)
    report = {
        "schema_version": 1, "snapshot_id": snapshot.snapshot_id, "policy": policy,
        "calendar_source_id": source_id, "sources": sources, "assessment_at_snapshot": state,
        "assessment_at_reconstruction": assess_calendar([event], coverage, current, **kwargs),
        "snapshot_status_at_reconstruction": snapshot.status_at(current),
        "event": {"event_id": event.event_id, "official_release_utc": scheduled.isoformat(),
                  "schedule_known_at_utc": schedule_observed.isoformat(),
                  "release_observed_at_utc": observed.isoformat() if observed is not None else None,
                  "release_observed_by_snapshot": observed is not None},
        "scope": "Scheduled FOMC coverage for the observed minutes-only month; BLS source bytes missing",
        "limitations": ["Published calendar cannot guarantee absence of unscheduled events",
                        "Host retrieval times do not prove provider publication or delivery latency",
                        "The 30-minute diagnostic rule has not been performance-tested",
                        "Does not supply FRED/ALFRED or CFTC numeric observations"],
        "execution_ready": False,
    }
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"Calendar coverage at snapshot: {state['status']}; {state['family_status']}")


if __name__ == "__main__":
    main()

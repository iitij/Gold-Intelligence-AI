"""Join observed official numeric macro data to a captured research snapshot."""

import argparse
import csv
import hashlib
import io
import json
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from goldintel.data.snapshot import SnapshotEvidence, build_market_snapshot, load_market_snapshot
from goldintel.domain import MarketQuote
from goldintel.research.point_in_time import CompletedGoldBar, EconomicObservation, _require_utc

OHLC = ("open", "high", "low", "close")
CFTC = "https://www.cftc.gov"
FRED_SERIES = {
    "fred-real-yield": ("DFII10", "percent"),
    "fred-dollar": ("DTWEXBGS", "broad dollar index, January 2006 = 100"),
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def timestamp(text):
    stamp = datetime.fromisoformat(text)
    _require_utc(stamp, "official receipt timestamp")
    return stamp


def request_times(start, stop):
    before, after = timestamp(start), timestamp(stop)
    if not timedelta(0) <= after - before <= timedelta(seconds=25):
        raise ValueError("Invalid source retrieval bracket")
    return before, after


def read_csv_capture(root, requests, name, series, *, vintage=None):
    entry = requests[name]
    file = f"{name}.csv"
    url = urlsplit(entry["url"])
    host = "alfred.stlouisfed.org" if vintage else "fred.stlouisfed.org"
    endpoint = "/graph/alfredgraph.csv" if vintage else "/graph/fredgraph.csv"
    query = parse_qs(url.query)
    if (entry["file"] != file or entry["http_status"] != "200" or entry["exit_code"] != 0
            or url.scheme != "https" or url.netloc != host or url.path != endpoint
            or query.get("id") != [series]):
        raise ValueError("Unexpected official series source or download state")
    if vintage and any(query.get(k) != [vintage.isoformat()] for k in ("vintage_date", "revision_date")):
        raise ValueError("ALFRED response request does not identify the exact vintage")
    data = (root / file).read_bytes()
    if not 0 < len(data) <= 2_000_000 or digest(data) != entry["sha256"]:
        raise ValueError("Official series bytes differ from the acquisition receipt")
    _, observed = request_times(entry["before_utc"], entry["observed_at_utc"])
    column = f"{series}_{vintage:%Y%m%d}" if vintage else series
    rows = csv.reader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True)
    if next(rows, None) != ["observation_date", column]:
        raise ValueError("Response series or vintage column differs")
    values = {}
    previous = None
    for fields in rows:
        day_text, value = fields
        day = date.fromisoformat(day_text)
        limit = vintage or observed.date()
        if (previous is not None and day <= previous) or day > limit:
            raise ValueError("Official series chronology is invalid")
        number = None if value in (".", "") else Decimal(value)
        if number is not None and not number.is_finite():
            raise ValueError("Nonfinite official numeric observation")
        previous = day
        values[day] = number
    if not values:
        raise ValueError("No official series rows")
    return values, observed, {
        "url": entry["url"], "sha256": entry["sha256"], "observed_at_utc": observed.isoformat(),
        "file": file, "missing_values": sum(value is None for value in values.values()),
    }


def read_cftc_document(root, name, expected_url):
    if (root / f"{name}.http").read_text().strip() != f"200 {expected_url}":
        raise ValueError("Expected a successful CFTC response from the archived source")
    begin, after = ((root / f"{name}.{label}").read_text().strip() for label in ("before", "after"))
    _, observed = request_times(begin, after)
    data = (root / f"{name}.html").read_bytes()
    if not 0 < len(data) <= 2_000_000:
        raise ValueError("Unexpected CFTC response length")
    return data.decode("utf-8"), observed, {
        "url": expected_url, "sha256": digest(data), "observed_at_utc": observed.isoformat(),
        "file": f"{name}.html",
    }


def gold_positions(page, reference):
    lines = page.splitlines()
    key = r"^GOLD - COMMODITY EXCHANGE INC\.\s+Code-088691\s*$"
    indices = [i for i, line in enumerate(lines) if re.fullmatch(key, line.strip())]
    if len(indices) != 1:
        raise ValueError("Expected exactly one CFTC Gold 088691 report")
    i = indices[0]
    scope = "\n".join(lines[i:i + 12])
    expected_date = f"{reference:%B} {reference.day}, {reference.year}"
    if (f"Disaggregated Commitments of Traders - Futures Only, {expected_date}" not in scope
            or "Managed Money" not in scope or "(CONTRACTS OF 100 TROY OUNCES)" not in scope):
        raise ValueError("CFTC report date, contract, or position type differs")
    row = next((line for line in lines[i:i + 12] if line.startswith("All ")), "")
    tokens = re.findall(r"[0-9]+(?:,[0-9]{3})*", row)
    if len(tokens) != 14 or not re.fullmatch(r"All[\s:0-9,]+", row):
        raise ValueError("Unexpected CFTC position column count")
    oi, prod_l, prod_s, swap_l, swap_s, swap_sp, managed_l, managed_s, managed_sp, other_l, other_s, other_sp, small_l, small_s = (
        int(value.replace(",", "")) for value in tokens
    )
    spreads = swap_sp + managed_sp + other_sp
    if (oi <= 0 or prod_l + swap_l + managed_l + other_l + small_l + spreads != oi
            or prod_s + swap_s + managed_s + other_s + small_s + spreads != oi):
        raise ValueError("CFTC position sides do not reconcile to open interest")
    return oi, managed_l, managed_s


def tentative_release(page, reference, release_day):
    # Month/day and stated embargo time must appear in the official year table.
    month_pattern = re.escape(release_day.strftime("%B"))
    header = unescape(re.sub(r"<[^>]+>", " ", page))
    match = re.findall(rf"<td[^>]*>\s*{month_pattern}\s*</td>(.*?)</tr>", page, re.DOTALL)
    if (len(match) != 1 or f"{release_day.year} Release Schedule" not in " ".join(header.split())
            or "released at 3:30 p.m. Eastern time" not in " ".join(header.split())
            or not re.search(rf">\s*{release_day.day:02d}\*?\s*</td>", match[0])
            or not timedelta(0) < release_day - reference <= timedelta(days=10)):
        raise ValueError("Tentative CFTC release day does not match archive scope")
    return datetime.combine(release_day, time(15, 30), ZoneInfo("America/New_York")).astimezone(timezone.utc)


def observation(series, reference, observed, value, source):
    # The date is an identity for the reference period, not an intraday market timestamp.
    reference_key = datetime.combine(reference, time.min, timezone.utc)
    return EconomicObservation(series, reference_key, observed, value, source, source)


def join(base, observations, macro_evidence):
    data = base.as_dict()
    decision = timestamp(data["decision_at_utc"])
    if data["released_observations"] or data["policy"]["calendar_coverage_verified"]:
        raise ValueError("Expected the verified direct market-only packet")
    quote = data["quote"]
    bars = [CompletedGoldBar(row["timeframe"], *(timestamp(row[key]) for key in
                             ("opened_at_utc", "closed_at_utc", "available_at_utc")),
                             *(Decimal(row[k]) for k in OHLC), row["source_id"])
            for row in data["bars"]]
    return build_market_snapshot(
        decision_at_utc=decision,
        quote=MarketQuote("XAUUSD", timestamp(quote["observed_at_utc"]),
                          Decimal(quote["bid"]), Decimal(quote["ask"]), quote["source_verified"]),
        quote_available_at_utc=timestamp(quote["available_at_utc"]), quote_source_id=quote["source_id"],
        evidence=[SnapshotEvidence(k, v) for k, v in {**data["source_sha256"], **macro_evidence}.items()],
        bars=bars, observations=observations,
        max_quote_age=timedelta(microseconds=data["policy"]["max_quote_age_microseconds"]),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--cot-reference-day", required=True, type=date.fromisoformat)
    parser.add_argument("--cot-scheduled-day", required=True, type=date.fromisoformat)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.sources
    base = load_market_snapshot(args.snapshot, args.snapshot_id)
    decision = timestamp(base.as_dict()["decision_at_utc"])
    if any((root / name).read_text().strip() != "NTPSynchronized=yes" for name in
           ("ntp-before.txt", "ntp-after.txt", "cot-ntp-after.txt")):
        raise ValueError("Official observations lack host clock synchronization evidence")
    requested = (root / "requests.json").read_bytes()
    requests = json.loads(requested)
    observations, bindings, reports, units = [], {}, {}, {}
    for name, (series, unit) in FRED_SERIES.items():
        values, observed, info = read_csv_capture(root, requests, name, series)
        source = f"fred_{series}_{info['sha256']}"
        bindings[source], reports[source], units[series] = info["sha256"], info, unit
        observations.extend(observation(series, day, observed, value, source)
                            for day, value in values.items() if value is not None)

    earlier, _, first_info = read_csv_capture(root, requests, "alfred-payroll-march", "PAYEMS",
                                               vintage=date(2026, 3, 6))
    later, _, last_info = read_csv_capture(root, requests, "alfred-payroll-april", "PAYEMS",
                                           vintage=date(2026, 4, 3))
    common = earlier.keys() & later.keys()
    if not common:
        raise ValueError("No overlapping ALFRED reference periods")
    revisions = [{"reference_date": str(d), "march_vintage": str(earlier[d]), "april_vintage": str(later[d]),
                  "delta_thousands": str(later[d] - earlier[d])}
                 for d in sorted(common) if earlier[d] is not None and later[d] is not None
                 and earlier[d] != later[d]]

    day = args.cot_reference_day
    url = f"{CFTC}/sites/default/files/files/dea/cotarchives/{day.year}/futures/other_lf{day:%m%d%y}.htm"
    cot, observed, cot_info = read_cftc_document(root, "cot-archive", url)
    schedule, schedule_seen, schedule_info = read_cftc_document(
        root, "cot-schedule", f"{CFTC}/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm",
    )
    planned = tentative_release(schedule, day, args.cot_scheduled_day)
    if observed < planned:
        raise ValueError("CFTC archive was observed before its nominated schedule")
    oi, long, short = gold_positions(cot, day)
    source = f"cftc_088691_{cot_info['sha256']}"
    bindings[source] = cot_info["sha256"]
    reports[source] = {**cot_info, "scheduled_release_utc": planned.isoformat(), "schedule_evidence": schedule_info,
                       "publisher_actual_delivery_time_verified": False,
                       "position_data_observed_at_utc": observed.isoformat(),
                       "calendar_observed_at_utc": schedule_seen.isoformat(),
                       "open_interest": oi, "managed_money_long": long, "managed_money_short": short}
    cot_series = "CFTC_088691_managed_money_net_contracts"
    units[cot_series] = "COMEX 100 troy ounce futures contracts"
    observations.append(observation(cot_series, day, observed, Decimal(long - short), source))

    enriched = join(base, observations, bindings)
    payload = enriched.as_dict()
    report = {
        "schema_version": 1, "market_snapshot_id": base.snapshot_id, "macro_snapshot_id": enriched.snapshot_id,
        "decision_at_utc": decision.isoformat(), "units": units, "point_in_time_sources": reports,
        "acquisition_manifest_sha256": digest(requested),
        "builder_sha256": digest(Path(__file__).read_bytes()),
        "latest_observed_values": payload["released_observations"],
        "as_of_status": enriched.status_at(decision),
        "held_back_row_count": sum(row.available_at_utc > decision for row in observations),
        "alfred_comparison": {"series": "PAYEMS", "march_06": first_info, "april_03": last_info,
                              "shared_reference_dates": len(common), "changed_values": revisions,
                              "intraday_historical_availability_verified": False,
                              "used_as_current_snapshot_feature": False},
        "limitations": ["Reference date keys use UTC midnight without claiming a provider event time",
                        "Only host-observed versions are used in this packet",
                        "FRED CSV files do not establish historical intraday release or revision time",
                        "CFTC scheduled release and observed archive retrieval are separate",
                        "The registry calendar is still incomplete"],
        "execution_ready": False,
    }
    args.output.mkdir()
    (args.output / "snapshot.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    (args.output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"Macro packet: {enriched.snapshot_id}, {len(payload['released_observations'])} observed values")


if __name__ == "__main__":
    main()

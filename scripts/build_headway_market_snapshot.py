"""Build a causal research snapshot from a timed Headway-Demo quote and bar capture."""

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from capture_headway_market_inputs import COUNTS, OHLC

from goldintel.data.snapshot import SnapshotEvidence, build_market_snapshot
from goldintel.domain import MarketQuote
from goldintel.research.point_in_time import FRAME_SECONDS, CompletedGoldBar

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parse_utc(text):
    stamp = datetime.fromisoformat(text)
    if stamp.utcoffset() != timedelta(0):
        raise ValueError("Capture timestamps must be UTC")
    return stamp


def ordered_bracket(record, lower, upper, limit):
    before, after = (parse_utc(record[key]) for key in ("host_utc_before", "host_utc_after"))
    if not lower <= before <= after <= upper or after - before > limit:
        raise ValueError("Unordered, out-of-envelope, or slow MT5 request")
    return before, after


def closed_bars(frame, timeframe, before, after, offset):
    rows = frame["bars"]
    seconds = FRAME_SECONDS[timeframe]
    if not 0 < len(rows) <= COUNTS[timeframe]:
        raise ValueError("Unexpected raw bar count")
    times = [row["native_open_seconds"] for row in rows]
    if (any(type(t) is not int or t <= 0 or t % seconds for t in times)
            or sorted(set(times)) != times):
        raise ValueError("Unaligned, duplicate or out-of-order native bar")
    openings = [EPOCH + timedelta(seconds=t - offset) for t in times]
    if openings[-1] > after:
        raise ValueError("Bar history unexpectedly opens after the read")
    results = []
    # Require a subsequent bar and a close before the request began. A bar
    # that closes during retrieval cannot be treated as the completed source.
    for row, a, successor in zip(rows[:-1], openings[:-1], openings[1:], strict=True):
        b = a + timedelta(seconds=seconds)
        if b > before or successor < b or a.date() != before.date() or b.date() != before.date():
            continue
        results.append(CompletedGoldBar(
            timeframe, a, b, after, *(Decimal(row[key]) for key in OHLC),
            f"headway_direct_{timeframe.lower()}",
        ))
    return results


def verify_aggregation(minutes, parent):
    by_open = {bar.opened_at_utc: bar for bar in minutes}
    count = FRAME_SECONDS[parent.timeframe] // FRAME_SECONDS["M15"]
    cohort = [by_open.get(parent.opened_at_utc + timedelta(minutes=15 * i)) for i in range(count)]
    if any(bar is None for bar in cohort):
        raise ValueError(f"Missing contiguous M15 rows to corroborate {parent.timeframe}")
    aggregate = (
        cohort[0].open, max(row.high for row in cohort),
        min(row.low for row in cohort), cohort[-1].close,
    )
    if aggregate != (parent.open, parent.high, parent.low, parent.close):
        raise ValueError(f"{parent.timeframe} OHLC differs from completed M15 aggregation")
    return count


def build(raw, anchor, ntp, source_bytes):
    if (raw["schema_version"] != 1 or raw["kind"] != "observed_headway_market_inputs"
            or raw["server"] != "Headway-Demo" or raw["symbol"] != "XAUUSD"
            or set(raw["frames"]) != set(COUNTS)):
        raise ValueError("Unexpected market capture source or schema")
    if (anchor.get("status") != "matching_current_headway_demo_quote_clock_and_export"
            or anchor.get("server") != raw["server"] or anchor.get("symbol") != raw["symbol"]
            or anchor.get("ntp_before_after") is not True
            or type(anchor.get("changed_quotes_matched")) is not int or anchor["changed_quotes_matched"] <= 0):
        raise ValueError("A matched, synchronized Headway-Demo clock receipt is required")
    offset = anchor["native_minus_utc_seconds"]
    if type(offset) is not int or abs(offset) > 14 * 3600 or offset % 900:
        raise ValueError("Invalid reviewed session offset")
    opened, finished = (parse_utc(ntp[key]) for key in ("checked_before_utc", "checked_after_utc"))
    if ntp["before"] != "NTPSynchronized=yes" or ntp["after"] != "NTPSynchronized=yes":
        raise ValueError("Host clock is not synchronized around capture")
    if finished - opened > timedelta(minutes=1):
        raise ValueError("Host clock evidence is too distant from capture")
    quote = raw["quote"]
    quote_before, decision = ordered_bracket(quote, opened, finished, timedelta(seconds=1))
    anchor_start, anchor_end = (parse_utc(anchor[key]) for key in (
        "first_host_observation_utc", "last_host_observation_utc",
    ))
    if not (anchor_start.date() == anchor_end.date() == opened.date() == decision.date()
            and anchor_start <= anchor_end <= opened):
        raise ValueError("Clock receipt must precede capture on the same UTC date")
    if type(quote["native_tick_msc"]) is not int:
        raise ValueError("Quote has no native millisecond timestamp")
    midpoint = quote_before + (decision - quote_before) / 2
    quote_time = EPOCH + timedelta(milliseconds=quote["native_tick_msc"], seconds=-offset)
    residual = (quote_time - midpoint).total_seconds()
    if abs(residual) > 2:
        raise ValueError("Fresh quote does not corroborate the session offset")

    sets = {}
    previous = opened
    for timeframe in COUNTS:
        frame = raw["frames"][timeframe]
        before, after = ordered_bracket(frame, previous, quote_before, timedelta(seconds=3))
        previous = after
        sets[timeframe] = closed_bars(frame, timeframe, before, after, offset)

    m15 = sets["M15"]
    if len(m15) < 2 or any(not sets[timeframe] for timeframe in ("H1", "H4")):
        raise ValueError("Insufficient same-date, closed market data")
    latest = {name: sets[name][-1] for name in ("H1", "H4")}
    counts = {name: verify_aggregation(m15, bar) for name, bar in latest.items()}
    bindings = {
        "capture_sha256": digest(source_bytes["capture"]),
        "session_clock_sha256": digest(source_bytes["clock"]),
        "host_clock_sha256": digest(source_bytes["ntp"]),
    }
    # All three inputs are needed to interpret the selected bars and quote.
    chain = digest(json.dumps(bindings, sort_keys=True).encode())
    bars = [*m15[-2:], *latest.values()]
    quote_source = "headway_direct_quote"
    snapshot = build_market_snapshot(
        decision_at_utc=decision, quote_available_at_utc=decision, quote_source_id=quote_source,
        quote=MarketQuote("XAUUSD", decision, Decimal(quote["bid"]), Decimal(quote["ask"]), True),
        bars=bars, evidence=[SnapshotEvidence(name, chain) for name in sorted(
            {quote_source, *(bar.source_id for bar in bars)}
        )],
    )
    return snapshot, {
        **bindings, "source_chain_sha256": chain, "native_minus_utc_seconds": offset,
        "quote_clock_residual_seconds": residual, "aggregation_matching_m15_rows": counts,
        "utc_scope": "Same session offset corroborated by recent observations and the fresh quote",
        "historical_clock_verified": False, "execution_ready": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--clock-evidence", type=Path, required=True)
    parser.add_argument("--host-clock-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sources = {"capture": args.capture.read_bytes(), "clock": args.clock_evidence.read_bytes(),
               "ntp": args.host_clock_evidence.read_bytes()}
    snapshot, receipt = build(*(json.loads(sources[k]) for k in ("capture", "clock", "ntp")), sources)
    output = snapshot.as_dict()
    args.output.mkdir()
    (args.output / "snapshot.json").write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    receipt.update({"snapshot_id": snapshot.snapshot_id, "builder_sha256": digest(Path(__file__).read_bytes())})
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
    print(f"Snapshot {snapshot.snapshot_id}; blockers: {', '.join(output['blockers'])}")


if __name__ == "__main__":
    main()

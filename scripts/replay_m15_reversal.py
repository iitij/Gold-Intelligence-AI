"""Replay the frozen M15 reversal rule on UTC Bid/Ask quotes."""

import argparse
import csv
import hashlib
import json
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from statistics import mean

from goldintel.research.holdout import (
    assert_holdout_released,
    assert_no_sealed_overlap,
    read_protocol,
)

BAR = timedelta(minutes=15)
WAIT = timedelta(seconds=30)
START = datetime.fromisoformat("2026-11-11T00:00:00+00:00")
PRIMARY_END = datetime.fromisoformat("2027-01-06T00:00:00+00:00")
DELAYS = (0, 1, 5)


def read_ticks(path, *, preserve_all=False):
    buckets = defaultdict(list)
    previous = None
    current_bucket = None
    last_quote = None
    pending = set()
    with path.open(newline="") as stream:
        rows = csv.DictReader(stream)
        if rows.fieldnames != ["timestamp_utc", "bid", "ask"]:
            raise ValueError("Expected timestamp_utc,bid,ask")
        for row in rows:
            time = datetime.fromisoformat(row["timestamp_utc"])
            bid, ask = Decimal(row["bid"]), Decimal(row["ask"])
            if (time.utcoffset() != timedelta(0) or (previous and time < previous)
                    or not bid.is_finite() or not ask.is_finite() or not 0 < bid <= ask):
                raise ValueError(f"Invalid quote at CSV line {rows.line_num}")
            previous = time
            bucket = time.replace(minute=time.minute // 15 * 15, second=0, microsecond=0)
            first_in_bucket = bucket != current_bucket
            if first_in_bucket:
                if last_quote is not None and buckets[current_bucket][-1:] != [last_quote]:
                    buckets[current_bucket].append(last_quote)
                current_bucket = bucket
                pending = set(DELAYS)
            last_quote = (time, bid, ask)
            eligible = {
                delay for delay in pending
                if bucket + timedelta(seconds=delay) <= time
                <= bucket + timedelta(seconds=delay) + WAIT
            }
            if preserve_all or first_in_bucket or eligible:
                buckets[bucket].append(last_quote)
                pending.difference_update(eligible)
    if last_quote is not None and buckets[current_bucket][-1:] != [last_quote]:
        buckets[current_bucket].append(last_quote)
    if not buckets:
        raise ValueError("No quotes")
    return buckets


def first_quote(buckets, boundary, seconds):
    target = boundary + timedelta(seconds=seconds)
    return next((q for q in buckets.get(boundary, ()) if target <= q[0] <= target + WAIT), None)


def weekly_interval(weekly):
    if len(weekly) < 8:
        return None
    totals = [(sum(values), len(values)) for values in weekly.values()]
    rng = random.Random(42)
    estimates = []
    for _ in range(2000):
        draw = rng.choices(totals, k=len(totals))
        estimates.append(sum(total for total, _ in draw) / sum(count for _, count in draw))
    estimates.sort()
    return [str(estimates[50]), str(estimates[1949])]


def return_risk(returns):
    """Measure the cumulative path for a sequence of one-ounce trades."""
    cumulative = peak = drawdown = Decimal(0)
    for value in returns:
        cumulative += value
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    return {
        "cumulative_net_usd": str(cumulative),
        "max_drawdown_usd": str(drawdown),
        "winning_trades": sum(value > 0 for value in returns),
        "losing_trades": sum(value < 0 for value in returns),
        "flat_trades": sum(value == 0 for value in returns),
    }



def replay(buckets, end, commission, slippage, *, ledger=None):
    if not START < end or end.utcoffset() != timedelta(0):
        raise ValueError("End must be UTC and later than the fixed start")
    if buckets[min(buckets)][0][0] > START - 2 * BAR or buckets[max(buckets)][-1][0] < end:
        raise ValueError("Quotes must bracket the evaluation interval and two warm-up bars")
    report = {}
    for delay in DELAYS:
        weekly = defaultdict(list)
        daily = defaultdict(list)
        spread_costs = []
        missing_signal = missing_fill = 0
        decision = START
        while decision + BAR + WAIT + timedelta(seconds=delay) < end:
            recent = buckets.get(decision - BAR)
            prior = buckets.get(decision - 2 * BAR)
            entry = first_quote(buckets, decision, delay)
            exit_quote = first_quote(buckets, decision + BAR, delay)
            if (not recent or not prior or decision - recent[-1][0] > WAIT
                    or decision - BAR - prior[-1][0] > WAIT):
                missing_signal += 1
            elif not entry or not exit_quote:
                missing_fill += 1
            else:
                short = recent[-1][1] > prior[-1][1]
                gross = entry[1] - exit_quote[2] if short else exit_quote[1] - entry[2]
                spread_costs.append(((entry[2] - entry[1]) + (exit_quote[2] - exit_quote[1])) / 2)
                week = decision.date() - timedelta(days=decision.weekday())
                net = gross - 2 * (commission + slippage)
                weekly[str(week)].append(net)
                daily[str(decision.date())].append(net)
                if ledger is not None:
                    ledger.append({
                        "decision": decision.isoformat(),
                        "delay_seconds": delay,
                        "side": "short" if short else "long",
                        "entry_time": entry[0].isoformat(),
                        "exit_time": exit_quote[0].isoformat(),
                        "entry_price": str(entry[1] if short else entry[2]),
                        "exit_price": str(exit_quote[2] if short else exit_quote[1]),
                        "spread_cost": str(spread_costs[-1]),
                        "commission": str(2 * commission),
                        "slippage": str(2 * slippage),
                        "net_usd_per_ounce": str(net),
                    })
            decision += BAR
        returns = [value for values in weekly.values() for value in values]
        report[str(delay)] = {
            "scheduled_decisions": len(returns) + missing_signal + missing_fill,
            "filled": len(returns),
            "return_risk": return_risk(returns) if returns else None,
            "missing_signal_bars": missing_signal,
            "missing_entry_or_exit_quote": missing_fill,
            "mean_net_usd_per_ounce": str(mean(returns)) if returns else None,
            "mean_spread_cost_usd_per_ounce": str(mean(spread_costs)) if returns else None,
            "mean_midpoint_return_usd_per_ounce": (
                str(mean(returns) + mean(spread_costs) + 2 * (commission + slippage))
                if returns else None
            ),
            "weekly_bootstrap_ci95": weekly_interval(weekly),
            "daily": {
                day: {"filled": len(values), "mean_net_usd_per_ounce": str(mean(values))}
                for day, values in daily.items()
            },
            "weekly": {
                week: {"filled": len(values), "mean_net_usd_per_ounce": str(mean(values))}
                for week, values in weekly.items()
            },
        }
    return report


def main():
    global START
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("quotes", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--start", type=datetime.fromisoformat, default=START)
    parser.add_argument("--end", required=True, type=datetime.fromisoformat)
    parser.add_argument("--commission-per-side-per-ounce", required=True, type=Decimal)
    parser.add_argument("--slippage-per-side-per-ounce", required=True, type=Decimal)
    parser.add_argument("--ledger", action="store_true", help="Include filled trades in JSON")
    parser.add_argument("--holdout-protocol", type=Path)
    parser.add_argument("--holdout-sha256")
    parser.add_argument("--frozen-root", type=Path)
    args = parser.parse_args()
    protocol_start = START
    if args.start.utcoffset() != timedelta(0) or args.start >= args.end:
        parser.error("Start must be explicit UTC and precede end")
    START = args.start
    costs = args.commission_per_side_per_ounce, args.slippage_per_side_per_ounce
    if any(not value.is_finite() or value < 0 for value in costs):
        parser.error("Costs must be finite and nonnegative")
    now = datetime.now(timezone.utc)
    assert_no_sealed_overlap(
        Path(__file__).resolve().parents[1] / "planning/holdout_registry.json",
        now=now, start=START, end=args.end,
    )
    holdout_options = (args.holdout_protocol, args.holdout_sha256, args.frozen_root)
    if any(holdout_options):
        if not all(holdout_options):
            parser.error("Supply protocol, its SHA256 and frozen root together")
        protocol = read_protocol(args.holdout_protocol, args.holdout_sha256)
        assert_holdout_released(
            protocol, now=now, start=START, end=args.end,
            frozen_root=args.frozen_root, replay_path=Path(__file__),
        )
    with args.quotes.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    ledger = [] if args.ledger else None
    report = {
        "protocol_window": (
            "registered_prospective_window" if args.holdout_protocol else
            "full_calendar_window" if args.end == PRIMARY_END and START == protocol_start else "exploratory"
        ),
        "holdout_protocol_sha256": args.holdout_sha256,
        "holdout_registration_is_not_gate_acceptance": True,
        "primary_end_exclusive": PRIMARY_END.isoformat(),
        "quotes_sha256": digest,
        "replay_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "start": START.isoformat(),
        "end_exclusive": args.end.isoformat(),
        "commission_per_side_per_ounce": str(costs[0]),
        "slippage_per_side_per_ounce": str(costs[1]),
        "delays_seconds": replay(read_ticks(args.quotes), args.end, *costs, ledger=ledger),
    }
    if ledger is not None:
        report["trade_ledger"] = ledger
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()

"""Diagnostic fixed-distance exits using all observed quotes."""
import argparse
import hashlib
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from replay_m15_reversal import BAR, first_quote, read_ticks

from goldintel.research.exits import simulate_exit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--policy", choices=("bracket", "time"), default="bracket")
    parser.add_argument("--distance", type=Decimal, default=Decimal("5"))
    args = parser.parse_args()
    if not args.distance.is_finite() or args.distance <= 0:
        parser.error("--distance must be finite and positive")
    buckets = read_ticks(args.input, preserve_all=True)
    ledger = []
    for decision in sorted(buckets):
        recent = buckets.get(decision - BAR)
        previous = buckets.get(decision - 2 * BAR)
        entry = first_quote(buckets, decision, 0)
        if not recent or not previous or not entry:
            continue
        if decision - recent[-1][0] > timedelta(seconds=30):
            continue
        if decision - BAR - previous[-1][0] > timedelta(seconds=30):
            continue
        side = "short" if recent[-1][1] > previous[-1][1] else "long"
        deadline = decision + BAR
        # Exclude overlapping entry schedules when their deadline fill was late.
        if ledger and ledger[-1].get("exit_time") and entry[0].isoformat() < ledger[-1]["exit_time"]:
            continue
        quotes = (q for boundary in (decision, deadline) for q in buckets.get(boundary, ())
                  if q[0] >= entry[0])
        result = simulate_exit(
            quotes, side=side, entry_time=entry[0],
            entry_price=entry[1] if side == "short" else entry[2],
            deadline=deadline,
            stop_distance=args.distance if args.policy == "bracket" else None,
            target_distance=args.distance if args.policy == "bracket" else None,
            max_gap=timedelta(seconds=30),
        )
        ledger.append({
            "entry_time": entry[0].isoformat(), "side": side,
            "reason": result.reason,
            "exit_time": result.time.isoformat() if result.time else None,
            "gross_usd_per_ounce": str(result.gross_usd_per_ounce)
            if result.gross_usd_per_ounce is not None else None,
        })
    reasons = {reason: sum(t["reason"] == reason for t in ledger)
               for reason in sorted({t["reason"] for t in ledger})}
    known = [Decimal(t["gross_usd_per_ounce"]) for t in ledger
             if t["gross_usd_per_ounce"] is not None]
    output = {
        "quote_rows": sum(len(values) for values in buckets.values()),
        "first_quote": buckets[min(buckets)][0][0].isoformat(),
        "last_quote": buckets[max(buckets)][-1][0].isoformat(),
        "known_exits": len(known),
        "unknown_exits": len(ledger) - len(known),
        "known_exit_mean_usd_per_ounce": str(sum(known) / len(known)) if known else None,
        "known_exit_sum_usd_per_ounce": str(sum(known)),
        "aggregation_scope": "Known exits only, not a full portfolio return",
        "policy": args.policy,
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "distance_usd_per_ounce": str(args.distance),
        "limitations": ["Provisional UTC mapping", "Fixed diagnostic distances",
                        "Commission and additional slippage excluded",
                        "Unknown exits evaluated independently of later opportunities"],
        "exit_reasons": reasons, "ledger": ledger,
    }
    with args.output.open("x") as stream:
        json.dump(output, stream, indent=2)


if __name__ == "__main__":
    main()

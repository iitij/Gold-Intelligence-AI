"""Export raw XAUUSD quote timestamps from an existing Headway-Demo MT5 session."""

import argparse
import csv
import os
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile


def export_range(mt5, start, end, output, *, exclusive_end=False):
    ticks = mt5.copy_ticks_range("XAUUSD", start, end, mt5.COPY_TICKS_ALL)
    status = mt5.last_error()[0]
    if ticks is None or status != 1:
        raise RuntimeError(f"MT5 copy_ticks_range failed with status {status}")
    if len(ticks) == 0:
        return 0
    if exclusive_end:
        start_ms = int(start.timestamp()) * 1000
        end_ms = int(end.timestamp()) * 1000
        ticks = ticks[(ticks["time_msc"] >= start_ms) & (ticks["time_msc"] < end_ms)]
        if not len(ticks):
            return 0
    with NamedTemporaryFile(
        mode="w", newline="", encoding="utf-8", dir=output.parent, delete=False,
    ) as stream:
        writer = csv.writer(stream)
        writer.writerow(["time_msc", "bid", "ask", "flags"])
        for tick in ticks:
            writer.writerow([
                int(tick["time_msc"]), float(tick["bid"]),
                float(tick["ask"]), int(tick["flags"]),
            ])
    temporary = Path(stream.name)
    try:
        os.link(temporary, output)
    finally:
        temporary.unlink()
    return len(ticks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--start", required=True, type=datetime.fromisoformat)
    parser.add_argument("--end", required=True, type=datetime.fromisoformat)
    parser.add_argument("--terminal", type=str)
    parser.add_argument("--portable", action="store_true")
    parser.add_argument("--batch", action="store_true", help="Write two-minute CSVs to OUTPUT")
    args = parser.parse_args()
    start, end = args.start, args.end
    if any(value.utcoffset() != timedelta(0) for value in (start, end)) or start >= end:
        parser.error("Supply increasing UTC bounds with an explicit +00:00 offset")

    if args.batch and (start.microsecond or end.microsecond or start.second or end.second):
        parser.error("Batch bounds must be aligned to whole minutes")

    import MetaTrader5 as mt5

    terminal = (args.terminal,) if args.terminal else ()
    print("Connecting to MT5", flush=True)
    if not mt5.initialize(*terminal, timeout=15000, portable=args.portable):
        raise SystemExit(f"MT5 initialization failed with code {mt5.last_error()[0]}")
    try:
        account = mt5.account_info()
        if account is None or account.server != "Headway-Demo":
            raise SystemExit("Open the intended Headway-Demo session in MT5")
        print(f"Headway-Demo verified; requesting XAUUSD from {start} to {end}", flush=True)
        if not args.batch:
            count = export_range(mt5, start, end, args.output)
            if not count:
                raise SystemExit(f"No quotes returned; MT5 status {mt5.last_error()[0]}")
            print(f"Exported {count} XAUUSD records from Headway-Demo")
            return

        args.output.mkdir(parents=True, exist_ok=True)
        cursor = start
        while cursor < end:
            stop = min(cursor + timedelta(minutes=2), end)
            name = f"{cursor:%Y%m%dT%H%M%S}_{stop:%Y%m%dT%H%M%S}.csv"
            output = args.output / name
            if not output.exists():
                print(f"Request {cursor.isoformat()} through {stop.isoformat()} exclusive", flush=True)
                count = export_range(mt5, cursor, stop, output, exclusive_end=True)
                message = f"Saved {count} rows" if count else "Empty quote window"
                print(message, flush=True)
            cursor = stop
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()

import csv
import runpy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


def test_compacted_quotes_preserve_fill_order_and_bar_close(tmp_path):
    replay = runpy.run_path(str(Path(__file__).resolve().parents[1]
                                / "scripts/replay_m15_reversal.py"))
    start = datetime(2026, 11, 11, tzinfo=timezone.utc)
    quotes = tmp_path / "quotes.csv"
    with quotes.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["timestamp_utc", "bid", "ask"])
        for seconds, bid in [(0, 100), (0, 101), (5, 102), (899, 103), (936, 104)]:
            writer.writerow([start + timedelta(seconds=seconds), bid, bid + 1])

    buckets = replay["read_ticks"](quotes)
    first_quote = replay["first_quote"]
    assert first_quote(buckets, start, 0)[1] == Decimal(100)
    assert first_quote(buckets, start, 1)[1] == Decimal(102)
    assert first_quote(buckets, start, 5)[1] == Decimal(102)
    assert buckets[start][-1][1] == Decimal(103)
    assert first_quote(buckets, start + replay["BAR"], 5) is None


def test_full_quote_path_preserves_intrabar_stop_and_rebound(tmp_path):
    from goldintel.research.exits import simulate_exit

    replay = runpy.run_path(str(Path(__file__).resolve().parents[1]
                                / "scripts/replay_m15_reversal.py"))
    start = datetime(2026, 11, 11, tzinfo=timezone.utc)
    path = tmp_path / "stop-rebound.csv"
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["timestamp_utc", "bid", "ask"])
        for seconds, bid in [(0, 100), (5, 100), (10, 100), (20, 95), (25, 100)]:
            writer.writerow([start + timedelta(seconds=seconds), bid, bid + 1])
    full = replay["read_ticks"](path, preserve_all=True)[start]
    compact = replay["read_ticks"](path)[start]
    assert len(full) == 5
    assert len(compact) == 3
    parameters = dict(
        side="long", entry_time=start, entry_price=Decimal(101),
        deadline=start + timedelta(seconds=25), stop_distance=Decimal(3),
        target_distance=Decimal(10), max_gap=timedelta(seconds=30),
    )
    observed = simulate_exit(full, **parameters)
    assert observed.reason == "stop"
    assert observed.time == start + timedelta(seconds=20)
    assert observed.price == Decimal(95)
    assert simulate_exit(compact, **parameters).reason == "deadline"

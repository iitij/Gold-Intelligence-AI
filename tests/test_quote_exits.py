from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from goldintel.research.exits import simulate_exit

START = datetime(2026, 11, 11, tzinfo=timezone.utc)


def run(side, quotes, gap=30):
    return simulate_exit(
        quotes, side=side, entry_time=START, entry_price=D("100"),
        deadline=START + timedelta(seconds=60), stop_distance=D("2"),
        target_distance=D("3"), max_gap=timedelta(seconds=gap),
    )


@pytest.mark.parametrize("side,bid,ask,price,gross", [
    ("long", "96", "97", "96", "-4"),
    ("short", "103", "104", "104", "-4"),
])
def test_stop_fills_at_observed_liquidation_quote(side, bid, ask, price, gross):
    result = run(side, [(START + timedelta(seconds=1), D(bid), D(ask))])
    assert result.reason == "stop"
    assert result.price == D(price)
    assert result.gross_usd_per_ounce == D(gross)


def test_long_target_and_missing_quotes():
    assert run("long", [(START, D("104"), D("105"))]).reason == "target"
    assert run("long", []).reason == "unknown_missing_exit"
    assert run("long", [(START + timedelta(seconds=31), D("96"), D("97"))]).reason == "unknown_gap"


def test_deadline_uses_observed_quote():
    result = run("short", [
        (START + timedelta(seconds=30), D("99"), D("100")),
        (START + timedelta(seconds=60), D("98"), D("99")),
    ])
    assert result.reason == "deadline"
    assert result.price == D("99")


def test_time_only_policy_ignores_intrabar_price_thresholds():
    result = simulate_exit(
        [
            (START + timedelta(seconds=20), D("90"), D("91")),
            (START + timedelta(seconds=40), D("110"), D("111")),
            (START + timedelta(seconds=60), D("100"), D("101")),
        ],
        side="long", entry_time=START, entry_price=D("101"),
        deadline=START + timedelta(seconds=60), stop_distance=None,
        target_distance=None, max_gap=timedelta(seconds=30),
    )
    assert result.reason == "deadline"
    assert result.gross_usd_per_ounce == D("-1")

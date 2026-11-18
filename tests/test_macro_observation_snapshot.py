"""Reject revision lookahead and invalid gold position totals."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from goldintel.data.snapshot import SnapshotEvidence, build_market_snapshot
from goldintel.domain import MarketQuote
from goldintel.research.point_in_time import EconomicObservation
from scripts.build_macro_observation_snapshot import gold_positions, join

DECISION = datetime(2026, 11, 18, 21, 0, tzinfo=timezone.utc)


def test_future_revision_changes_neither_macro_packet_nor_its_evidence():
    base = build_market_snapshot(
        decision_at_utc=DECISION,
        quote=MarketQuote("XAUUSD", DECISION, Decimal("3700"), Decimal("3701"), True),
        quote_available_at_utc=DECISION, quote_source_id="quote",
        evidence=[SnapshotEvidence("quote", "a" * 64)],
    )
    reference = DECISION - timedelta(days=2)
    initial = EconomicObservation("DFII10", reference, DECISION - timedelta(minutes=1),
                                  Decimal("2.8"), "initial", "v1")
    revision = EconomicObservation("DFII10", reference, DECISION + timedelta(microseconds=1),
                                   Decimal("3.1"), "future", "v2")
    prior = join(base, [initial], {"initial": "b" * 64})
    replay = join(base, [revision, initial], {"initial": "b" * 64, "future": "c" * 64})
    assert replay.snapshot_id == prior.snapshot_id
    assert replay.as_dict()["released_observations"][0]["value"] == "2.8"
    assert replay.as_dict()["source_sha256"] == {"initial": "b" * 64, "quote": "a" * 64}
    assert not replay.as_dict()["execution_ready"]


def test_cot_uses_futures_only_gold_code_and_reconciles_position_columns():
    row = ("GOLD - COMMODITY EXCHANGE INC. Code-088691\n"
           "Disaggregated Commitments of Traders - Futures Only, November 10, 2026\n"
           "Managed Money (CONTRACTS OF 100 TROY OUNCES)\n"
           "All  :   14: 1 2 1 1 1 5 4 1 1 1 1: 3 3\n")
    assert gold_positions(row, date(2026, 11, 10)) == (14, 5, 4)
    with pytest.raises(ValueError, match="reconcile"):
        gold_positions(row.replace("14:", "15:"), date(2026, 11, 10))
    with pytest.raises(ValueError, match="report date"):
        gold_positions(row.replace("Futures Only", "Options and Futures Combined"), date(2026, 11, 10))

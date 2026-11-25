"""Check that Headway deal evidence cannot confuse net zero with no charge."""

from types import SimpleNamespace

from scripts.audit_headway_deal_costs import summarize_deal_costs


def deal(symbol, kind, entry, commission=0, fee=0, volume=0.01):
    return SimpleNamespace(symbol=symbol, type=kind, entry=entry, commission=commission,
                           fee=fee, swap=0, volume=volume, ticket=123, comment="private")


def test_offsets_and_unattributed_adjustments_remain_visible():
    result = summarize_deal_costs([
        deal("XAUUSD", 0, 0, commission=-1.25),
        deal("XAUUSD", 0, 0, commission=1.25),
        deal("XAUUSD", 1, 1, fee=-0.2, volume=0.02),
        deal("", 7, 0, volume=0),
        deal("OTHER", 0, 0, commission=-10),
    ], 1, "XAUUSD")
    assert result["status"] == "observed_sample"
    first, second = result["symbol_groups"]
    assert first["commission"] == {"negative": 1, "zero": 0, "positive": 1, "min": "-1.25", "max": "1.25"}
    assert second["fee"]["negative"] == 1 and second["volume_lots_max"] == "0.02"
    assert result["unattributed_deal_type_counts"] == {7: 1}
    assert "ticket" not in first and "comment" not in first


def test_failed_query_is_distinct_from_a_successful_empty_sample():
    failure = summarize_deal_costs([deal("XAUUSD", 0, 0)], -1, "XAUUSD")
    empty = summarize_deal_costs([], 1, "XAUUSD")
    assert failure["status"] == "query_failed" and failure["symbol_groups"] is None
    assert empty["status"] == "no_symbol_deals" and empty["symbol_groups"] == []

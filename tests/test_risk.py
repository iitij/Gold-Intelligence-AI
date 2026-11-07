from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from goldintel.domain import (
    AccountState,
    BrokerSymbolSpec,
    MarketQuote,
    RiskPolicy,
    Side,
    TradeProposal,
)
from goldintel.risk import assess_paper_proposal

NOW = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
SPEC = BrokerSymbolSpec(
    "XAUUSD", "XAUUSD", D("0.01"), D("1"), D("0.01"),
    D("10"), D("0.01"), D("30"), True,
)
QUOTE = MarketQuote("XAUUSD", NOW, D("2000.00"), D("2000.10"), True)
ACCOUNT = AccountState("USD", D("10000"), D("10000"), D("0"), D("0"), 0, True)
PROPOSAL = TradeProposal(
    Side.BUY, "XAUUSD", NOW, NOW + timedelta(minutes=1),
    D("2000.10"), D("1998.10"), D("2004.10"), "id-001", "demo",
)
POLICY = RiskPolicy()


def check(proposal=PROPOSAL, quote=QUOTE, spec=SPEC,
          account=ACCOUNT, policy=POLICY, now=NOW):
    return assess_paper_proposal(proposal, quote, spec, account, policy, now)


def test_approved_paper_proposal():
    decision = check()
    assert decision.allowed
    assert decision.volume_lots == D("0.12")
    assert decision.maximum_loss_account_ccy <= ACCOUNT.reference_equity * POLICY.max_risk_fraction


def test_unverified_broker_spec_rejected():
    assert check(spec=replace(SPEC, specs_verified=False)).reason == "market_or_symbol_spec_unverified"


def test_wrong_symbol_rejected():
    assert check(proposal=replace(PROPOSAL, symbol="BTCUSD")).reason == "unsupported_instrument"


def test_no_trade_rejected():
    assert check(proposal=replace(PROPOSAL, side=Side.NO_TRADE)).reason == "no_trade_or_invalid_side"


def test_live_policy_rejected():
    assert check(policy=replace(POLICY, paper_only=False)).reason == "policy_must_remain_paper_only"


def test_min_lot_must_not_round_up():
    p = replace(PROPOSAL, stop_loss=D("1000"))
    assert check(proposal=p).reason == "min_lot_exceeds_risk_budget"


def test_daily_realized_and_unrealized_loss():
    a = replace(ACCOUNT, daily_realized_pnl=D("-50"), daily_unrealized_pnl=D("-60"))
    assert check(account=a).reason == "daily_loss_limit"


def test_broker_check_required():
    assert check(account=replace(ACCOUNT, broker_order_check_ok=False)).reason == "broker_order_check_required"


def test_stale_quote_rejected():
    assert check(quote=replace(QUOTE, observed_at_utc=NOW - timedelta(minutes=2))).reason == "stale_quote"


def test_future_quote_rejected():
    assert check(quote=replace(QUOTE, observed_at_utc=NOW + timedelta(seconds=1))).reason == "stale_quote"


def test_crossed_quote_rejected():
    assert check(quote=replace(QUOTE, ask=D("1999"))).reason == "crossed_quote"


def test_expired_forecast_rejected():
    assert check(proposal=replace(PROPOSAL, forecast_valid_until_utc=NOW - timedelta(seconds=1))).reason == "expired_forecast"


def test_stale_signal_rejected():
    assert check(proposal=replace(PROPOSAL, signal_at_utc=NOW - timedelta(minutes=3))).reason == "stale_signal"


def test_stop_too_close_rejected():
    assert check(proposal=replace(PROPOSAL, stop_loss=D("2000.00"))).reason == "stop_too_close"


def test_position_limit_rejected():
    assert check(account=replace(ACCOUNT, open_positions=1)).reason == "position_limit"


def test_price_drift_rejected():
    assert check(proposal=replace(PROPOSAL, entry_price=D("2010.10"))).reason == "price_drift"


def test_spread_limit_rejected():
    q = replace(QUOTE, ask=D("2001"))
    p = replace(PROPOSAL, entry_price=D("2001"))
    assert check(proposal=p, quote=q).reason == "spread_too_wide"


def test_missing_model_id_rejected():
    assert check(proposal=replace(PROPOSAL, model_id=" ")).reason == "missing_proposal_provenance"


def test_sell_direction_accepted():
    q = MarketQuote("XAUUSD", NOW, D("2000.00"), D("2000.10"), True)
    p = replace(
        PROPOSAL, side=Side.SELL, entry_price=D("2000.00"),
        stop_loss=D("2002.00"), take_profit=D("1996.00"),
    )
    assert check(proposal=p, quote=q).allowed


def test_nan_rejected():
    assert check(spec=replace(SPEC, tick_value_loss_account_ccy=D("NaN"))).reason == "nonpositive_or_nonfinite_inputs"

def test_volume_max_off_grid_is_floored_on_grid():
    spec = replace(SPEC, volume_max=D("0.025"))
    result = check(spec=spec)
    assert result.allowed
    assert result.volume_lots == D("0.02")
    assert (result.volume_lots - spec.volume_min) % spec.volume_step == 0


def test_grid_with_nonstandard_minimum_and_step():
    spec = replace(SPEC, volume_min=D("0.03"), volume_step=D("0.02"), volume_max=D("0.10"))
    result = check(spec=spec)
    assert result.allowed
    assert result.volume_lots == D("0.09")
    assert (result.volume_lots - spec.volume_min) % spec.volume_step == 0


def test_max_volume_smaller_than_minimum_rejected():
    spec = replace(SPEC, volume_max=D("0.005"))
    assert check(spec=spec).reason == "invalid_risk_policy_or_volume_spec"


def test_out_of_range_risk_fraction_rejected():
    policy = replace(POLICY, max_risk_fraction=D("1.01"))
    assert check(policy=policy).reason == "invalid_risk_policy_or_volume_spec"


def test_out_of_range_daily_loss_fraction_rejected():
    policy = replace(POLICY, max_daily_loss_fraction=D("1.01"))
    assert check(policy=policy).reason == "invalid_risk_policy_or_volume_spec"


def test_invalid_position_policy_rejected():
    policy = replace(POLICY, max_open_positions=0)
    assert check(policy=policy).reason == "invalid_risk_policy_or_volume_spec"


def test_invalid_quote_age_policy_rejected():
    policy = replace(POLICY, max_quote_age_seconds=-1)
    assert check(policy=policy).reason == "invalid_risk_policy_or_volume_spec"


def test_invalid_signal_age_policy_rejected():
    policy = replace(POLICY, max_signal_age_seconds=0)
    assert check(policy=policy).reason == "invalid_risk_policy_or_volume_spec"


def test_unaligned_broker_quote_rejected():
    quote = replace(QUOTE, ask=D("2000.105"))
    assert check(quote=quote).reason == "price_off_tick_grid"


def test_unaligned_stop_rejected():
    proposal = replace(PROPOSAL, stop_loss=D("1998.105"))
    assert check(proposal=proposal).reason == "price_off_tick_grid"


def test_sizing_never_exceeds_budget_across_volume_grid():
    for maximum in ("0.015", "0.025", "0.045", "0.10", "1.00", "10.00"):
        spec = replace(SPEC, volume_max=D(maximum))
        decision = check(spec=spec)
        assert decision.allowed
        assert decision.volume_lots <= spec.volume_max
        assert (decision.volume_lots - spec.volume_min) % spec.volume_step == 0
        assert decision.maximum_loss_account_ccy <= D("25")

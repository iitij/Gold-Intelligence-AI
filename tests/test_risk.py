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
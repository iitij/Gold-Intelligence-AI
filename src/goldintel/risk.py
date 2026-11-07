"""Fail-closed PAPER-ONLY risk screening; no execution or broker connectivity.

This illustrative pre-trade checker never raises size to minimum volume if that
would breach the risk budget. True broker metadata, margin and order verification
are required independently. A caller must not interpret allowed=True as
permission for live trading.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_FLOOR, Decimal

from goldintel.domain import (
    AccountState,
    BrokerSymbolSpec,
    MarketQuote,
    RiskDecision,
    RiskPolicy,
    Side,
    TradeProposal,
)


def _positive(*values: Decimal) -> bool:
    return all(v.is_finite() and v > 0 for v in values)


def _utc_aware(dt: datetime) -> bool:
    return dt.tzinfo is not None and dt.utcoffset() is not None


def assess_paper_proposal(
    proposal: TradeProposal,
    quote: MarketQuote,
    spec: BrokerSymbolSpec,
    account: AccountState,
    policy: RiskPolicy,
    now_utc: datetime,
) -> RiskDecision:
    def reject(reason: str) -> RiskDecision:
        return RiskDecision(False, reason)

    if not policy.paper_only:
        return reject("policy_must_remain_paper_only")
    if any(not _utc_aware(dt) for dt in (
        now_utc, proposal.signal_at_utc, proposal.forecast_valid_until_utc,
        quote.observed_at_utc,
    )):
        return reject("timezone_unknown")
    if now_utc.utcoffset() != timezone.utc.utcoffset(now_utc):
        return reject("now_must_be_utc")
    if spec.asset_id != "XAUUSD" or proposal.symbol != spec.broker_symbol:
        return reject("unsupported_instrument")
    if quote.symbol != proposal.symbol or not quote.source_verified or not spec.specs_verified:
        return reject("market_or_symbol_spec_unverified")
    if proposal.side not in (Side.BUY, Side.SELL):
        return reject("no_trade_or_invalid_side")
    if not proposal.idempotency_key.strip() or not proposal.model_id.strip():
        return reject("missing_proposal_provenance")
    if not _positive(
        spec.tick_size, spec.tick_value_loss_account_ccy,
        spec.volume_min, spec.volume_max, spec.volume_step,
        proposal.entry_price, proposal.stop_loss, proposal.take_profit,
        quote.bid, quote.ask, account.reference_equity, account.day_start_equity,
    ):
        return reject("nonpositive_or_nonfinite_inputs")
    if spec.stops_level_ticks < 0 or not spec.stops_level_ticks.is_finite():
        return reject("invalid_stop_level")
    if (
        spec.volume_min > spec.volume_max
        or not _positive(
            policy.max_risk_fraction,
            policy.max_daily_loss_fraction,
            policy.max_entry_drift_ticks,
            policy.max_spread_ticks,
        )
        or policy.max_risk_fraction > 1
        or policy.max_daily_loss_fraction > 1
        or policy.max_open_positions < 1
        or policy.max_quote_age_seconds <= 0
        or policy.max_signal_age_seconds <= 0
    ):
        return reject("invalid_risk_policy_or_volume_spec")
    if quote.ask < quote.bid:
        return reject("crossed_quote")
    # A risk estimate based on invalid price increments is not broker-ready.
    if any(price % spec.tick_size != 0 for price in (
        quote.bid, quote.ask, proposal.entry_price, proposal.stop_loss, proposal.take_profit,
    )):
        return reject("price_off_tick_grid")
    for dt, bound, reason in (
        (quote.observed_at_utc, policy.max_quote_age_seconds, "stale_quote"),
        (proposal.signal_at_utc, policy.max_signal_age_seconds, "stale_signal"),
    ):
        age = (now_utc - dt).total_seconds()
        if age < 0 or age > bound:
            return reject(reason)
    if now_utc > proposal.forecast_valid_until_utc:
        return reject("expired_forecast")
    if quote.ask - quote.bid > spec.tick_size * policy.max_spread_ticks:
        return reject("spread_too_wide")
    executable = quote.ask if proposal.side == Side.BUY else quote.bid
    if abs(executable - proposal.entry_price) > spec.tick_size * policy.max_entry_drift_ticks:
        return reject("price_drift")
    if proposal.side == Side.BUY:
        valid_stop = proposal.stop_loss < executable < proposal.take_profit
        stop_dist = executable - proposal.stop_loss
    else:
        valid_stop = proposal.take_profit < executable < proposal.stop_loss
        stop_dist = proposal.stop_loss - executable
    if not valid_stop:
        return reject("invalid_stop_or_target")
    if stop_dist < spec.stops_level_ticks * spec.tick_size:
        return reject("stop_too_close")
    if account.open_positions < 0 or account.open_positions >= policy.max_open_positions:
        return reject("position_limit")
    daily_net = account.daily_realized_pnl + account.daily_unrealized_pnl
    if not daily_net.is_finite():
        return reject("unknown_daily_pnl")
    if -daily_net >= account.day_start_equity * policy.max_daily_loss_fraction:
        return reject("daily_loss_limit")
    if not account.broker_order_check_ok:
        return reject("broker_order_check_required")
    risk_budget = account.reference_equity * policy.max_risk_fraction
    # Broker must supply verified loss-side tick value in the account currency.
    ticks_at_risk = stop_dist / spec.tick_size
    loss_per_lot = ticks_at_risk * spec.tick_value_loss_account_ccy
    if not _positive(loss_per_lot):
        return reject("cannot_calculate_loss")
    raw_lots = risk_budget / loss_per_lot
    if raw_lots < spec.volume_min:
        return reject("min_lot_exceeds_risk_budget")
    # Cap BEFORE flooring on the legal grid; clamping the floored result to
    # volume_max can produce an illegal off-grid lot when max is not aligned.
    capped_lots = min(raw_lots, spec.volume_max)
    increments = ((capped_lots - spec.volume_min) / spec.volume_step).to_integral_value(
        rounding=ROUND_FLOOR
    )
    lots = spec.volume_min + increments * spec.volume_step
    if lots < spec.volume_min:
        return reject("invalid_broker_lot_grid")
    maximum_loss = lots * loss_per_lot
    if maximum_loss > risk_budget:
        return reject("calculated_risk_exceeds_budget")
    return RiskDecision(True, "approved_for_paper_only", lots, maximum_loss)
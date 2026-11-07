"""Typed contracts for XAUUSD-only research; zero broker connectivity."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NO_TRADE = "NO_TRADE"


@dataclass(frozen=True)
class BrokerSymbolSpec:
    asset_id: str
    broker_symbol: str
    tick_size: Decimal
    tick_value_loss_account_ccy: Decimal
    volume_min: Decimal
    volume_max: Decimal
    volume_step: Decimal
    stops_level_ticks: Decimal
    specs_verified: bool = False


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    observed_at_utc: datetime
    bid: Decimal
    ask: Decimal
    source_verified: bool


@dataclass(frozen=True)
class AccountState:
    account_currency: str
    reference_equity: Decimal
    day_start_equity: Decimal
    daily_realized_pnl: Decimal
    daily_unrealized_pnl: Decimal
    open_positions: int
    broker_order_check_ok: bool


@dataclass(frozen=True)
class TradeProposal:
    side: Side
    symbol: str
    signal_at_utc: datetime
    forecast_valid_until_utc: datetime
    entry_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    idempotency_key: str
    model_id: str


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str
    volume_lots: Decimal | None = None
    maximum_loss_account_ccy: Decimal | None = None


@dataclass(frozen=True)
class RiskPolicy:
    max_risk_fraction: Decimal = Decimal("0.0025")
    max_daily_loss_fraction: Decimal = Decimal("0.01")
    max_open_positions: int = 1
    max_quote_age_seconds: int = 60
    max_signal_age_seconds: int = 120
    max_entry_drift_ticks: Decimal = Decimal("20")
    max_spread_ticks: Decimal = Decimal("50")
    paper_only: bool = True

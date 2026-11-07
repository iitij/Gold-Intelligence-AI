# Paper-only risk gateway verification notes

Updated 2026-11-07 in response to [technical audit](17-INDEPENDENT-TECHNICAL-AUDIT.md).

## Applied defensive changes
- Clip proposed volume at broker max BEFORE flooring on the grid `volume_min + N * volume_step`; regression checks include off-grid broker maximum and unusual step sizes.
- Fail closed on risk fractions above 100%, zero/negative position limit, or nonpositive quote/signal timeouts.
- Fail closed on prices not aligned with the declared broker tick size.

## Crucial residual limits — DO NOT CONNECT TO LIVE TRADING
- `RiskDecision.maximum_loss_account_ccy` is a **modeled stop-distance loss estimate** based on caller-supplied tick value. It is **not** a maximum realized loss: fees, swap, gaps and execution slippage can exceed it.
- `broker_order_check_ok` is still a caller-provided bool, **not** a cryptographically bound real broker order-check result. The current research class must not be used to authorize orders.
- No checks yet for account margin, other positions/pending orders, concurrency, outstanding risk reservations, model signatures, broker timezone or reconciliation.
- Broker `OrderCalcProfit`/`order_calc_profit`, broker order checks, tick-value conversions, and price/volume grid must be cross-validated on a demo account.
- Do not switch from research/paper mode. Reject unknown broker configuration.

## Tests and acceptance
Run `python -m pytest tests/test_risk.py -q` and GitHub CI. Add property/fuzz tests and broker-specific demo fixtures before using this component in any MT5 execution gateway.

**This change is defensive validation, not proof of profitability, broker readiness or a trading system.**

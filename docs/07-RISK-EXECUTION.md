# Risk and MT5 execution contract

## Safety invariants

- No live broker integration exists in v0.1. `mode=paper`, no enabled live switch.
- Execution requires a validated non-expired signal, independent human/authorization step, policy version and idempotency key.
- `risk_budget = conservative_reference_equity * max_risk_fraction`; check drawdown, daily realized+unrealized P&L, open positions, spread, stop-level, margin, blackout/freeze regime.
- Use broker's `trade_tick_value_loss`, `trade_tick_size`, `volume_min/step/max`, currency conversion and actual order check. **Floor** lot sizes; if below broker min or risk > budget => reject, never clamp upwards.
- SL obligatory, not merely a warning. Symbol `XAUUSD` normalized with broker alias; wrong symbol rejects.
- Stale quote, stale forecast, unsupported volume, missing conversion, inconsistent price, missing market context => NO_TRADE.
- Circuit breakers are persistent across process restarts and use reliable account/broker history rather than in-memory closed trade buffers.
- Position limits and loss budgets must account for positions outside the agent as appropriate to scope.

## MT5 architecture

Ubuntu research/agents ↔ signed/authenticated localhost bridge ↔ MQL5 EA under MT5/Wine. Validate message schema and nonce, idempotency, deadlines, broker retcodes, and **reconcile before retrying** any ambiguous request. Disconnections trigger freeze of new orders, not blind cancellation or duplication. Manual emergency-stop and read-only status interface.

## Risk numbers

No default percentage authorizes production. Experimental parameters (e.g. 0.25% risk/trade, 1% daily loss) require documented owner approval and demo testing; real loss can exceed stops on gaps or market execution. Leverage and slippage can cause severe loss.

## MT5 acceptance

Order_check and symbol-specific tick values verified for broker; order_fill modes and market constraints; stop/freeze levels; swap/commission; price drift; timezone; duplicate requests; partial fills; unknown outcome; restart state; broker trade reconciliation. Tests with simulated degraded network and intentionally invalid responses.

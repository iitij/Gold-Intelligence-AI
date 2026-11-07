# P11 — Gold Alpha Research Tournament and Market Evidence

Status: **planned**. No results are claimed and the absence of XAUUSD data blocks execution.

## Research tournament (P11-01)

1. Pre-register each hypothesis, time window, feature set, baseline, maximum tuning trials, net metric and rejection criteria.
2. Use the same licensed, point-in-time data, executable bid/ask, risk capital, fill assumptions and economic event release constraints for each candidate.
3. Compare no-change, always-NO_TRADE, fixed rules, LightGBM, CatBoost, time-series models, and optional agent-assisted decisions **through identical simulation contracts**.
4. Log every attempted configuration, including failed/abandoned experiments. Use purged Walk-Forward, calibration, bootstrap confidence intervals and multiple-comparison corrections.
5. Lock a final holdout with an access ledger; accessing it repeatedly invalidates its independent status. A newer chronological holdout must then be reserved.
6. Report net return, turnover, maximum drawdown, trade independence, uncertainty, stability across sessions and cost stresses, not accuracy alone.
7. Compare quant-only against quant+Qwen council by controlled ablation, including inference latency and hallucination/missing-data refusal.
8. Treat a statistically inconclusive result as **no proven edge**, not as an invitation to tune on holdout.

## Market microstructure and basis (P11-02)

- XAUUSD OTC/CFD execution quotes are broker-specific. Never substitute a futures settlement or reference midprice as an executable quote.
- A GC futures time series requires license, expiration, proper roll/basis policy and publication/availability timestamps. External inputs may inform XAUUSD while only XAUUSD is traded.
- For CFTC positioning, use the actual release timestamp, not Tuesday's positions as Tuesday-available data.
- Track spread, session, quote latency, tick quality, volatility regimes, missing data and broker specification effective dates.
- Demonstrate incremental information through strict price-only versus price+external data ablations.

## Champion/Challenger (P11-03)

- Register every model's data and code hashes, feature schema, calibration, approval state and intended risk mode.
- Champion remains immutable for a given evaluation; challengers run in shadow with no order permission.
- Promotion requires locked offline evidence, forward/demo evidence, human approval and a tested rollback.
- Investigate calibration drift and event-distribution shift before any automated retraining proposal. No automatic promotion.

## Broker execution cost observatory (P11-04)

- Log quote timestamp, order request/response identifiers, bid/ask, intended vs actual fill, partial/failed fills, fees, spread, swap, and session/regime where authorized.
- Reconcile rather than blindly retry unknown order states.
- Compare realistic backtest simulated fills against forward paper/demo logs.
- Use sensitivity stress tests to reject edges that disappear under modest execution frictions.
- Never put account credentials, raw private statements, or unlicensed broker tick feeds into GitHub.

**Do not start P11 before the prerequisites in `planning/backlog.json` pass.**

# Strategy registry — hypotheses, not profitable claims

Only XAUUSD. No strategy is approved for real money. Each idea needs a tracked experiment and a pre-registered benchmark.

| ID | Proposal | Data | Falsification |
|---|---|---|---|
| STR-001 | Momentum / trend continuation after volatility-adjusted breakout | M15/H1/H4, ATR, bid/ask | Net OOS edge absent after spread + stops |
| STR-002 | Reversal at previous-session liquidity level after rejection | M5/M15, previous highs/lows, volatility | Intrabar ambiguity and worse fills remove edge |
| STR-003 | Macro event blackout and post-release volatility regime classifier | Real event publication time, spread, tick | OOS risk reduction not demonstrated |
| STR-004 | No-trade meta-labeling/gate | base model probability, spread, calibration | Selective trades do not improve net expectancy |
| STR-005 | Multi-horizon distributional forecast | Chronos-2/NHITS + baseline | No improvement in calibrated quantile score/OOS net |
| STR-006 | Ensemble and regime gating | CatBoost/LightGBM, regime context | Simple calibrated model matches/exceeds ensemble |
| STR-007 | RL position exit policy (future, conditional) | validated event simulator | Simulator exploitation or unstable cross-period result |

## Example: STR-001

**Decision time:** after confirmed close of M15 candle; H1/H4 values must be from completed bars. **Entry:** broker's next executable bid/ask (not close). **Output:** candidate signal only. **Stop/target:** derived from volatility known at decision, then checked by risk gateway and broker. **Controls:** spread/session/news/latency; a strict no-trade option. **Metrics:** returns net of costs, downside risk, calibration, stressed fills. **Avoid:** maximizing hit rate, fixed hidden target fitted on holdout, optimizing to single historical regime.

## Strategy admission

Register `strategy_id`, family, hypothesis, data cutoff, experiment_id, hash, gate result and reason for acceptance/rejection. Strategies should be independently disableable with no code deployment.

# Research protocol and falsification

## Hypothesis registration

Before running an experiment, record feature family, target, market universe, comparison baseline, no-trade rule, net metric, significance/robustness acceptance, data availability constraints, number of trials, expected computation and a disconfirming outcome.

## Leakage defense

1. Freeze data cutoffs; label horizon purge; embargo where appropriate.
2. Fit scaler, imputation, feature selection, threshold selection and calibration inside training only.
3. Join macro data on **available_at** or actual release time, not period date.
4. Do not let a model observe finalized H1/H4 candle until close.
5. Use exclusive holdout and a holdout access ledger. A repeated holdout inspection is not independent.
6. Never train from future account P&L unless it was historically available.

## Backtest integrity

Event-driven replay, reference Tick where needed, bid/ask order execution, min-stop/freeze levels, contract specs valid in time, market/limit semantics, volume step, rejections, latency, commission/swap, margin checks, net P&L and drawdown. Verify research/live risk math is shared.

## Statistical outcomes

Score model calibration and financial outcomes separately. Include fold-by-fold performance, period sensitivity, transaction-cost stress, bootstrap confidence intervals, strategy correlation, multiple-comparison correction and sufficiently numerous *independent* trades. Report the number of attempted configurations including rejected ones.

## Failure criteria

If no out-of-sample net edge over baseline, stop the strategy: no external money. If results collapse under modest friction/shift or sample count is low, reject. If any unhandled data leak or broker unreconciled order exists, block deployment.

## Paper progression

Offline replay → shadow-signal logging (no orders) → paper simulation → MT5 demo with manual approval → extended demo forward evaluation → security/legal/operational review → optional live decision by human owner. No fixed calendar promises.

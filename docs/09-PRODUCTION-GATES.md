# Go / No-Go gates

| Gate | Required evidence | Fail result |
|---|---|---|
| G0 Source | pinned SHA, source/security scan, provenance and reproducible infrastructure | block integration |
| G1 Data | UTC policy, broker instrument specs, independent verification, no leakage | block training |
| G2 Model | calibrated OOS tests, locked holdout ledger, baseline comparison, trial count | reject model |
| G3 Execution | realistic event-driven backtest incl fees/bid-ask, gap/partial fill tests | block broker bridge |
| G4 Security | secret scan, risk gate negative tests, emergency stop, idempotency, logs | block demo automation |
| G5 Demo | enough live forward samples over distinct regimes, cost evidence, reconciliation | keep demo |
| G6 Production | documented human approval, broker operating constraints, independent audit, runbook/rollback, acceptable risk | no live authorization |

Successful completion of a gate never proves a perpetual profitable edge. A new model or major broker configuration must repeat the applicable gates. No fixed timeline override of a failed gate.

Current work scope: [owner engineering priorities](36-ENGINEERING-PRIORITIES.md).

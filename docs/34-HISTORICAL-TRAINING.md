# Historical XAUUSD training, 17 November 2026

The reproducible entry point is
`PYTHONPATH=src .venv/bin/python scripts/train_historical_strategies.py --output <new-directory> data/raw/mt5/*.csv`.
Use a fresh output directory. The two feeds are trained independently.

Training outcomes precede 1 January 2026. Validation decisions start on
1 January and their outcomes precede 1 April. Test decisions start on
1 April. Horizons are 1, 4 and 16 M15 bars. Input lookbacks and outcomes
must be contiguous. These dates use each broker's native chronology.
The test interval has been inspected repeatedly and supports exploratory
comparisons. Independent confirmation requires unseen observations.

| Registry strategy | Current evidence | Remaining work |
| --- | --- | --- |
| STR-001 trend breakout | Fixed 16-bar range with quarter-ATR buffer, sequential next-open replay, monthly results, hypothetical costs and weekly bootstrap | Executable quote costs, unseen confirmation, stops and position sizing |
| STR-002 session rejection | Previous native-calendar session extremes, sequential next-open replay and cost sensitivity | UTC session mapping, finer-grained execution evidence |
| STR-003 macro blackout | Versioned blackout filter and nine sourced schedule records | Actual event publication timestamps and spread observations |
| STR-004 no-trade gate | Six LightGBM reversal meta-label models, validation-selected thresholds | Sequential next-open replay completed, negative hypothetical-cost results |
| STR-005 distribution forecast | LightGBM 0.1/0.5/0.9 quantile baselines compared with historical quantiles | Chronos/NHITS evaluated, persistence selected by validation MAE, unseen confirmation pending |
| STR-006 ensemble | LightGBM, CatBoost and equal-weight ensemble, logistic calibration | Sequential ensemble and regime replay completed, unseen confirmation pending |
| STR-007 exit policy | Observed-quote stop/target/deadline kernel, paired exit diagnostic and supervised LightGBM/CatBoost early-exit baselines | Full simulator validation, latency-aware evaluation and conditional RL research |

The latest combined classifier, calibration, quantile and meta-gate run is
`artifacts/historical-strategies-2026-11-17-meta/report.json`.
It records source hashes, model hashes, feature order, library versions,
split ranges, candidate validation scores and calibration coefficients.
Each classifier considers depths 3, 5 and 7 and selects by validation Brier
score. Quantile models retain fixed settings. Meta-labels measure positive
gross reversal returns and their thresholds maximize validation gross
return per opportunity.

The fixed-rule executable-price approximations are produced by
`scripts/evaluate_session_rejection.py`. Select `--strategy breakout`
or `--strategy rejection`. Entry uses the next bar open. Exit uses the
horizon bar close. One position can be open at a time in sequential results.
Cost scenarios deduct 0, 0.5, 1, 2 or 5 basis points per completed trade.
These scenarios require replacement with measured execution costs.
Weekly bootstrap intervals are marginal intervals for each tested case.
Multiple experiment selection remains a source of optimism.

Four-hour breakout gross mean weekly-bootstrap intervals include zero
for both feeds. The reversal meta-gate's two-basis-point diagnostic is
negative for every feed and horizon. No completed experiment establishes
production readiness.

Saved classifier inference is available through
`scripts/predict_historical_model.py`, with required `--as-of` in native
broker time. It validates model hashes and feature order. The feature
builder removes bars closing after the decision time and operates without
future labels. Automated regression checks future-price perturbation,
last-bar availability and historical feature compatibility.

The 16 November clock capture produced no available log. On 17 November
the direct read-only retry failed the expected Headway-Demo account check.
Historical UTC mapping remains unresolved. Demo connectivity was restored
on 18 November.

Additional research runs saved after the initial report include validation-only
regime selection in `artifacts/historical-strategies-2026-11-17-regime`.
Quantile crossing diagnostics and additive interval calibration are in
`artifacts/historical-strategies-2026-11-17-meta`. The interval correction
increased observed later-period coverage to approximately 85–87 percent.
Temporal dependence limits conformal exchangeability assumptions.

NHITS preparation uses `scripts/prepare_forecast_panel.py` and retains
contiguous segments of at least 80 bars. Segments also end at split
boundaries. The runner `scripts/train_nhits_historical.py` uses 64 input
bars, a 16-bar output horizon and 200 optimization steps by default.
It evaluates the final sixteen bars of each held-out segment and compares
price MAE against persistence. Runs with 200 and 500 steps have completed for both feeds. Saved 200-step
models were reloaded and reproduced test MAE within 1e-6. The isolated Python 3.11 environment is
`.venv-forecast311`.

Chronos-2 zero-shot evaluation completed on 18 November using the pinned
revision and verified weight SHA256. The runner uses 64 context bars and
disables cross-series learning. Predictions and interval coverage are
saved in `artifacts/chronos-20261118`. Pretraining overlap with historical
evaluation dates remains unverified.

The matched forecast comparison is reproducible with
`scripts/compare_forecast_benchmarks.py`. It verifies equal evaluation row
counts and persistence MAE across reports, then selects using validation
MAE. Among persistence, NHITS-200, NHITS-500 and Chronos-2, persistence is
selected for both feeds. Neural forecasts have not demonstrated additional
price-MAE value on this experiment.

Classifier calibration was also compared against a constant probability
estimated from validation labels, using the same later test outcomes.
Only five of eighteen calibrated cases beat this updated constant
reference. Twelve of eighteen beat the older training-period prior.
The difference indicates that updating the marginal class probability
explains much of the measured Brier improvement. Results are in
`artifacts/calibration-vs-validation-prior-20261118.json`.
Future training reports include the validation-prior benchmark explicitly.

Observed-quote exits are implemented in `goldintel.research.exits` and
exercised by `scripts/replay_quote_exits.py` with the full quote reader.
The three-day diagnostic contains 1,599,766 observed quotes. On 265 common
known exits, a fixed five-dollar bracket averaged -0.694 USD per ounce
and deadline-only exits averaged -0.818. Clock conversion is provisional,
costs beyond observed spread are excluded, and unknown exits remain
unresolved. These are diagnostic exit comparisons.

Sequential classifier, meta-gate, ensemble and regime results are stored
in `artifacts/classifiers-regime-sequential-20261118.json` and its
robustness report. The hypothetical two-basis-point cost scenario does
not establish a positive lower confidence bound for any tested case.
Calendar intake has three schedule versions with sourced known-by times
and six incomplete records. Full STR-003 training remains incomplete.

On 18 November the restored Headway-Demo session provided 189 changed
quote observations across two captures with host NTP synchronization.
All 189 native millisecond timestamps matched a 1,503-row four-minute
export. The observed native clock is UTC+02:00. The session evidence is
`artifacts/headway-session-utc-evidence-20261118.json`, and normalized
quotes are `artifacts/headway-session-utc-20261118.csv`. The maximum
observed quote gap is 3.369 seconds. This anchors the observed session.
Historical dates and DST transitions still require separate evidence.

The supervised early-exit runner is `scripts/train_quote_exit_policy.py`.
Its verified run is `artifacts/quote-exit-policy-verified-20261118/report.json`.
Training uses 5,280 observations from 176 episodes whose terminal labels
strictly precede 13 November in provisional native-clock encoding. The
later diagnostic has 89 episodes. Episodes crossing the split are purged;
five episodes with unavailable terminal liquidation are excluded. Features
are elapsed time, current executable liquidation PnL, observed spread and
bid change from entry. Terminal outcomes appear only in training labels
and evaluation comparisons. Tests perturb future quotes and verify that
earlier features and selected early exits remain unchanged.

Both fixed-setting classifiers exit immediately in all 89 later episodes.
They exactly reproduce the immediate-exit baseline: mean -0.379551 USD
per ounce, versus -0.543258 for the time exit and zero for no trade.
The apparent improvement over waiting provides no learned advantage over
immediate liquidation and remains inferior to abstention. Saved-model
reload predictions match the fitted models exactly. The report records
model, code and input hashes, package versions, parameters, split windows,
class balance, exclusions and exit ledgers. This is supervised diagnostic
research; it is not reinforcement learning or an executable portfolio.

The user identified the reconnected Headway-Demo account as Standard.
Current commission evidence is recorded separately in
`artifacts/headway-standard-cost-evidence-20261118.json`. The historical
account tier, slippage and financing remain separate unresolved inputs.
The native M15 history was extended by 550 bars after all 608 overlapping
bars matched exactly; its immutable merge manifest accompanies
`data/validated/headway_m15_native_extended_20261118.csv`.

`planning/research_run_index.json` records report hashes and explicitly
reported tuning candidates across the available classifier reruns,
neural forecast evaluations and supervised exit fits. Reproduce it with
`scripts/index_research_runs.py` and the listed reports into a fresh path.
It is a retrospective partial inventory, not a prospective trial ledger:
unrecorded manual choices and other diagnostic comparisons remain outside
its counts. Repeated evaluation inspection and multiple comparisons still
prevent treating the selected result as untouched confirmation.

Persisted feature/label samples are now available in
`data/features/native-training-set-v1-20261118`. The package contains
223,280 horizon-specific samples across both original feeds and separate
train/validation/test files, with source-row identities and SHA256 hashes.
All twelve validation-selected direction classifiers were refitted from
these files and reproduced reference probabilities on all three splits
within 1e-12. See `docs/36-PERSISTED-TRAINING-SET.md` for verification,
counts, exclusions and the unchanged exploratory/native-clock limitations.

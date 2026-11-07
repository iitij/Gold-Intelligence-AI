# استراتيجية التدريب المحلي XAUUSD

## الترتيب المعتمد

**الأولوية 1:** بناء baseline غير متعلم وLightGBM/CatBoost من الصفر على بيانات الذهب، ثم معايرة احتمالاتها. **الأولوية 2:** Chronos-2 zero-shot ثم fine-tune مشروط بتحسن OOS، وNHITS/NBEATSx كمرشحين. **الأولوية 3:** Qwen3-4B محليًا للاستدلال ثم SFT LoRA/QLoRA على حالات تحليل مؤرخة ومراجعة. **الأولوية 4:** RL فقط بعد محاكاة مثبتة.

## الهدف (labeling)

ابدأ بإشارة M15، أفق 4/8/16 شمعة، اتجاه/عائد بعد تكاليف محافظ؛ ثم triple-barrier مع stop وtake-profit وtimeout معتمدين على تقلب معلوم وقت القرار. القيم `label`, `t1`, `ret`, `barrier_hit` لا تدخل features إطلاقًا. Samples overlap => purged splits, uniqueness weights when justified. Exit at bid/ask and commission/slippage; reject ambiguous intrabar except with Tick replay.

## Features

Log returns lagged, range/body/wicks, realized volatility, ATR/ADX/MA slope, spread percentile, session, distance to previous highs/lows, M5/H1/H4 completed bars, volatility regime, scheduled macro releases with first-published data. All scalar transforms fitted only on training folds.

## Training protocol

- Split by time and data availability, not random shuffling.
- Baselines: no-change, simple momentum, time-of-day, always NO_TRADE, and rule-only approach.
- Tune on walk-forward training/validation; lock a final untouched holdout. Report number of strategy/model attempts.
- Evaluate LogLoss, Brier, reliability diagrams, calibrated precision, expected return net of costs, Sharpe/Sortino/PSR/DSR and bootstrap CIs.
- Include spread, latency, slippage, fees, partial fills, gaps, out-of-hours and MT5 broker constraints.
- Favor the smallest reliable model; exclude extra neural net if no repeatable improvement.

## Chronos model use

Treat `amazon/chronos-2` model weights and their license/version independently from code license. Start zero-shot; then optional local LoRA; test quantile calibration and tail intervals. No claim that price forecast means executable trade.

## Qwen model use

Qwen pretrained weights are NOT our trained-from-scratch property. Fine-tuned adapters are produced in house, with labeled market snapshots and audited annotations. Use retrieval with date restrictions; never expose future news or realized outcome in inference prompts. Evaluate structured output, abstention, faithfulness, hallucinations, tool-use safety, model latency and context integrity. Never let LLM invent quantitative confidence or position sizing.

## Hardware

GPU/RAM/VRAM must be measured before selecting LoRA model precision, batch, sequence length and offload. RTX 3070 Ti Laptop VRAM often differs by SKU; never assume capacity without `nvidia-smi`.

## Experiment record

`experiment_id`, strategy, code SHA, dataset hashes, schema versions, label parameters, time windows, split logic, random seeds, resolved environment lock, model hash, performance with CIs, benchmark, brokerage assumptions, result artifacts, decision (reject/continue).

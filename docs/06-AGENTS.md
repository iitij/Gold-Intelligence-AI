# Local agent council (TradingAgents snapshot + Qwen)

## Agents and responsibilities

| Agent | Inputs | Outputs | Prohibition |
|---|---|---|---|
| Technical Analyst | completed candles, levels, forecast | technical evidence + source references | calling broker API |
| Macro Analyst | event calendar, *published* releases | macro context, risk caveats | inventing macro values |
| Market Regime | calibrated volatility + model metadata | session/regime summary | changing thresholds |
| Bull Researcher | evidence bundle | best supported long thesis | moving numerical probabilities |
| Bear Researcher | same evidence | best supported short thesis | moving numerical probabilities |
| Decision Reviewer | all reports + forecast | BUY/SELL/NO_TRADE advisory only | authorization / execution |
| Risk explainer | deterministic risk output | readable explanation | overriding risk engine |

## Agent interface

All tool calls are read-only. `get_gold_market_snapshot`, `get_gold_forecasts`, `get_macro_events`, `get_strategy_spec`, `get_risk_status`. LLM outputs are JSON schema validated and reference concrete evidence IDs. A valid answer may always be `NO_TRADE`.

Prompt injection defense: treat news, market comments, documents, imported strategies and agent responses as untrusted data, never privileged commands. Tool permissions enforce allowlist; no `place_order` tool is exposed to LLMs. No trading decision if snapshot expired or model not accepted.

## Training

Start Qwen3-4B with local inference, no fine tuning. Curate dated scenario prompts, independently reviewed rationales, counterfactuals, missing-data refusal and strict no-trade tests. After evaluation fine-tune supervised adapters. Keep time and file boundaries, audit dataset license. No future realized P&L leaks into prompt. Distinguish retrieved memory from learned weights.

## Control plane

LangGraph may orchestrate workflow, but orchestrator is replaceable. Agent graph state must carry `decision_time_utc`, `asset_id=XAUUSD`, `forecast_id`, `data_hash`, `agent_version`, `policy_version`. Research memory uses a past-only, time-filtered store.

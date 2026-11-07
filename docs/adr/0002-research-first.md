# ADR-0002: Research-first hybrid, no live execution

**Status:** accepted · **Date:** 2026-11-07

Train LightGBM and CatBoost from scratch on XAUUSD data and compare to simple baselines. Add Chronos and local Qwen only when measured value justifies them. Keep LLM agents read-only; deterministic risk engine exclusively owns authorization; MT5 demo-only until gated. Prefer modular adapters rather than inheriting a whole trading system, and refuse production claims without independent net-of-cost evidence.

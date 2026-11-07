# ADR-0003 — Frozen weights and separate model artifact store

**Status:** Accepted for research infrastructure, 2026-11-07.

- Train LightGBM, CatBoost, NHITS and NBEATSx from scratch on licensed XAUUSD data.
- Fine-tune Qwen or Chronos only after unbiased evaluation.
- Pin Hugging Face `repo_id` to immutable complete commit revision before any download.
- Commit **only** manifests, provenance, license references, trained model metadata and SHA256 indices to Git.
- Store checkpoint weights in local restricted `models/weights/` or a controlled dedicated artifact store, never regular Git.
- Download only deliberately, with explicit command and correct license, then record file-level hashes. Back up model artifacts for future offline recovery.
- No automatic update or model replacement; model promotion requires held-out test results and separate authorization.
- No serialization formats allowing arbitrary code by default; prefer safetensors.
- Existing source/project terms remain in force regardless of vendoring.

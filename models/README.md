# Research model registry

No trained model, broker data or downloadable weights are distributed here. See `model_catalog.json` for intended candidates and approval schema. Start with LightGBM and CatBoost trained on our XAUUSD data; compare Chronos zero-shot and NHITS; fine-tune a local Qwen model only after building independently reviewed examples. Every external weight requires exact revision, upstream/model-card license, SHA256, and a secure local artifact store; never assume the GitHub repository license covers model weights.

## Central frozen foundation model catalog

- [foundation_candidates.json](foundation_candidates.json): Qwen3-4B, Qwen3.5-2B, Chronos-2 and all train-from-scratch XAUUSD models.
- `foundation_weights.lock.json` is created **once** when source revisions are verified against Hugging Face. It is absent until that run completes.
- `python scripts/model_assets.py list` lists models without network access.
- `python scripts/model_assets.py download --model chronos-2 --confirm` explicitly downloads a pinned checkpoint to the ignored local model storage; requires `huggingface_hub` installed and adequate disk.
- `python scripts/model_assets.py verify --model chronos-2` checks cached SHA256 without contacting upstream.
- Every trained adapter or model must have a separate evaluation/provenance manifest and local backup. The upstream base license is independent of our training dataset license.

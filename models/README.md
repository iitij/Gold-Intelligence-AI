# Model and checkpoint registry

This directory intentionally contains **no pretrained model weights**. Our project stores model *recipes, hashes, training code and acceptance reports* here. Actual weights/checkpoints are placed in `models/weights/` on approved local storage and are gitignored.

Workflow: verify exact model card/license -> choose revision SHA -> download to local storage -> record SHA256, tensor/quantization information, source revision, runtime compatibility -> freeze -> benchmark -> fine-tune adapter with dataset provenance -> require G2 approval before promotion. Never `pull latest` in production.

Our **LightGBM and CatBoost** are trained from scratch with XAUUSD data. Chronos and Qwen are pretrained external weights: only their adapters and/or finetuned outputs are our new artifacts, subject to licenses. Neither GitHub commit lock nor PyPI versions substitutes for exact HuggingFace model snapshot lock.

# GitHub publication and governance

Repository: https://github.com/iitij/Gold-Intelligence-AI
Visibility: **private**. Default branch: **main**. The repository and its issues are already created.

## Current state (2026-11-07)

- All 48 planned tasks are GitHub Issues; stable identifiers P00-01 through P10-05.
- README, architecture, source/model lockfiles, roadmap, unit-test scaffold and risk code are committed.
- Curated frozen source modules are included for offline review from Aurum and TradingAgents. **These are not full upstream snapshots, production deployments or trained models.**
- Live execution is not implemented; all operational controls are research or paper-only.

## Developer onboarding

```bash
git clone https://github.com/iitij/Gold-Intelligence-AI.git
cd Gold-Intelligence-AI
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check src tests scripts
python scripts/check_repository_policy.py
python -m goldintel health
```

Run source freezing once, only after dependency and license review:

```bash
python scripts/freeze_sources.py --dry-run
# With vetted network access + disk capacity, on a separate reviewed PR:
python scripts/freeze_sources.py --confirm
```

## Task administration

Issues are the collaborative task workflow; backlog.json is the committed plan and depends-on graph. The import utility does not recreate an existing issue with the same ID. To initialize or reconcile labels and 11 phase milestones on a workstation with authenticated GitHub CLI:

```bash
python scripts/publish_issues.py --repo iitij/Gold-Intelligence-AI --dry-run
python scripts/publish_issues.py --repo iitij/Gold-Intelligence-AI --confirm
```

Review repository settings manually: require CI on protected main, disallow force pushes, configure code review and private vulnerability reporting, minimize Actions permissions. GitHub App connector used here does not provide the admin actions necessary to enforce branch protection directly.

Never commit credentials, API tokens, private trading statements, proprietary market-data snapshots or model weights to Git. No automatic upstream sync. No live-account rollout without governance decision and independent review.

# GitHub publication and governance

Repository: https://github.com/iitij/Gold-Intelligence-AI
Visibility: **private**. Default branch: **main**. The repository and its issues are already created.

## Current state (2026-11-07)

- All 52 planned tasks are GitHub Issues across 12 phases; stable identifiers P00-01 through P11-04.
- README, architecture, source/model lockfiles, roadmap, unit-test scaffold and risk code are committed.
- Full snapshots of 584 source files from Aurum, TradingAgents and Midas are archived at immutable SHAs, alongside original curated copies; they are **not integrated trading deployments or trained models**.
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

Full source archive import has **already been completed once and sealed**. Do not run `scripts/freeze_sources.py --confirm` again: no upstream sync is permitted. Verify integrity with:

```bash
python scripts/verify_full_snapshots.py
python scripts/verify_vendor_integrity.py
```

## Task administration

Issues are the collaborative task workflow; backlog.json is the committed plan and depends-on graph. The import utility does not recreate an existing issue with the same ID. To initialize or reconcile labels and 12 phase milestones on a workstation with authenticated GitHub CLI:

```bash
python scripts/publish_issues.py --repo iitij/Gold-Intelligence-AI --dry-run
python scripts/publish_issues.py --repo iitij/Gold-Intelligence-AI --confirm
```

Review repository settings manually: require CI on protected main, disallow force pushes, configure code review and private vulnerability reporting, minimize Actions permissions. GitHub App connector used here does not provide the admin actions necessary to enforce branch protection directly.

Never commit credentials, API tokens, private trading statements, proprietary market-data snapshots or model weights to Git. No automatic upstream sync. No live-account rollout without governance decision and independent review.

## Recorded GitHub limitation (2026-11-08)

An API check returned `main.protected=false`, and the Rulesets request for this private repository returned GitHub's plan limitation. Until a supported GitHub plan/ruleset is configured, the PR+CI policy is a **manual team rule** rather than enforced branch protection; never represent it as technical enforcement. Actions identities are pinned by SHA to prevent unreviewed action-tag movement. Python packages remain unpinned until a reviewed dependency lock is merged.

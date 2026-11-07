# Frozen source inventory

The source of truth is [`sources.lock.json`](sources.lock.json). Exact 40-character upstream commit SHAs are recorded for reproducible one-time review. `snapshot-approved` authorizes **review**, not direct production use. We own subsequent fixes and never auto-sync upstream. `reference-only` means **do not copy code**. Each copied vendor fragment must retain its original LICENSE and notices, have dependency inventory, local unit tests, security review, and documented provenance.

Currently [`vendor/frozen_2026_11_07/`](../vendor/frozen_2026_11_07/) includes a **curated subset**, not complete upstream repositories. The full immutable source snapshots remain a separate tracked milestone. If a source is unlicensed or AGPL, treat as reference-only pending a recorded legal determination. Python wheel versions and model weight revisions are tracked separately, not equated with Git commits.

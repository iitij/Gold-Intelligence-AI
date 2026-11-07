# Frozen source inventory

The source of truth is [`sources.lock.json`](sources.lock.json). Exact 40-character upstream commit SHAs are recorded for reproducible one-time review. `snapshot-approved` authorizes **review**, not direct production use. We own subsequent fixes and never auto-sync upstream. `reference-only` means **do not copy code**. Each copied vendor fragment must retain its original LICENSE and notices, have dependency inventory, local unit tests, security review, and documented provenance.

Currently [`vendor/frozen_2026_11_07/`](../vendor/frozen_2026_11_07/) includes a **curated subset**, not complete upstream repositories. The full immutable source snapshots remain a separate tracked milestone. If a source is unlicensed or AGPL, treat as reference-only pending a recorded legal determination. Python wheel versions and model weight revisions are tracked separately, not equated with Git commits.

## Source migration status

The one-time archive workflow is at `.github/workflows/freeze-sources-once.yml`. After review and merge, it can build a **separate GitHub branch** containing full fixed-commit copies of TradingAgents, Aurum and (optional approved) Midas. It never merges the result automatically. That branch requires license, secret and dependency review before merging to main; after that delete the workflow. Reference-only projects are listed by URL and SHA rather than copied. [Complete source hub](../docs/16-SOURCE-HUB.md).

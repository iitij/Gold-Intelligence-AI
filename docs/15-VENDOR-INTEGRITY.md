# Frozen vendor source integrity

## Verified evidence — 2026-11-07

The 11 copied upstream files in the existing curated vendor snapshot (including both LICENSE files) were compared using **Git blob SHA-1** against the *exact locked upstream commits* — not moving branches. All 11 byte-level comparisons matched.

- Aurum source: zero-was-here/tradingbot at commit 39c33b49237e0f290f89bda18e27aa4e75021c03.
- TradingAgents source: TauricResearch/TradingAgents at commit 9fa1196fffbcfd9de5146d2dd2869df84ab99838.
- Immutable file paths and blob digests: sources/frozen_vendor.lock.json.
- Enforce offline at every CI run: python scripts/verify_vendor_integrity.py.

These 11 files represent **selected research/orchestration components**, NOT full runnable upstream packages. Provenance verification does NOT establish that the code is secure, licensed for all dependencies, executable, or profitable.

## Independent future maintenance

After the initial reviewed one-time import, do not sync the upstream repository, Git submodules, or dynamic updates. Develop necessary bug fixes in our own modules with explicit tests and provenance; do not quietly overwrite frozen copies.

Next tasks: review NOTICE and dependency closure, software bill of materials, license and secrets inventory, sandboxed tests and version-lock validation. No autonomous execution or real account integration is authorized.

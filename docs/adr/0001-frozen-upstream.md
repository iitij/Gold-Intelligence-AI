# ADR-0001: Freeze third-party sources and maintain internally

**Status:** accepted · **Date:** 2026-11-07

## Decision

Select specific GitHub commits for approved open-source projects. Import code once after a security/legal inventory, strip VCS metadata, retain full license/attribution, save SHA and local modifications, test and maintain internally. Do not synchronize with upstream after import and do not use runtime imports from GitHub URLs. The main code is our own adapters/contracts; we use third-party components only as audited modules.

## Context

User explicitly prefers complete ownership of future fixes instead of returning to upstream projects. Existing framework behavior may change and dependencies can break. Source freeze increases reproducibility but shifts patch/security burden to the project maintainers.

## Consequences

- **Pros:** deterministic baseline, no forced upstream upgrades, easier audit and project focus.
- **Cons:** security fixes, license compliance, bug fixes, and compatibility become OUR responsibility; stale code can contain vulnerabilities. We must track vulnerability advisories for impact assessment without pulling new upstream versions automatically. Any necessary remedy is an internal patch documented by PR, never an uncontrolled pull.
- **Rule:** Re-importing a new upstream snapshot later would require a new explicit ADR and exceptional review, not automatic habit.

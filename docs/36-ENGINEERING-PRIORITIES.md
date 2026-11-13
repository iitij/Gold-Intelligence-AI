# Engineering work scope — owner instruction, 2026-11-14

The owner explicitly stopped further license/rights investigation and requested
that development focus on completing the project. This instruction supersedes
license-review blockers in earlier planning notes and audit conclusions.

No new license research, supplementary license acquisition, redistribution
assessment or license-based source exclusion is scheduled or required by the
engineering readiness gates. Existing notices, metadata and archived reports
remain historical records; they do not create a new review task. This records
the owner's work scope, not a new assertion about every artifact's legal status.

P01-01 now tracks original source/code/weight revisions, hashes and internal
modifications. Other backlog criteria now request technical source/version/data
evidence rather than a licensing verdict. No task is marked done by this change.

Technical requirements continue to apply:

- Exact code/model/dependency versions and hashes, reproducible installation,
  working builds, compatibility checks and security findings that affect code.
- Dataset origin, original bytes/hash, instrument and price-side definitions,
  acquisition/export settings, UTC/DST, availability times, gaps and quality.
- Broker specifications and historical costs, leakage-safe transformations and
  chronological splits, calibration/OOS results and experiment records.
- Owner-machine evidence where required, isolated execution, protected secrets,
  fail-closed risk checks and the explicit prohibition on live trading.

The active preflight IDs use raw_data_provenance_and_hashes and
broker_operating_constraints. They replace the older combined rights/legal IDs;
no verification flag or gate status is promoted automatically. Historical SBOM,
package-inventory and hash checks remain integrity checks, not licensing gates.

The immediate remaining work is actual owner-machine verification and intake of
the original XAUUSD broker/reference files. Their bytes and timing evidence are
still absent from this workspace. They cannot be replaced with invented rows or
an assumed UTC offset. Library integration smoke tests remain synthetic only.

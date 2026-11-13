# Build and XAUUSD acceptance audit — 2026-11-14

## Scope and revisions

Reviewed main `a0d1ac82f95e97dd495ea5a836d597d113facb0c` and PR #79
`edef5108ecaaecfc0da09ee56e1eb4262b37bc54`. The referenced chat preview did
not contain its detailed plan, and no read_thread tool was available. Repository
issues, source files and workflow results supplied the acceptance criteria.

## Verified locally

Debian 13.6 x86_64, CPython 3.11.18 (uv-managed). Both existing locks installed
with SHA256 enforcement and binary wheels; no dependency versions were changed.

- PR #79 before changes: 181 tests and Ruff passed.
- After changes: 182 tests and Ruff passed, including source replacement regression.
- Six CI packages downloaded using the existing lock, then installed in a fresh
  venv with no pip/setuptools using --no-index, --require-hashes and wheel-only
  installation. Dependency compatibility, all tests and Ruff passed in that venv.
  The outer installer still uses bootstrap packages; this is package reinstall
  evidence, not a fully offline OS/interpreter or reproducible wheel-build claim.
- ML lock: 24 packages, compatibility check passed. Synthetic LightGBM accuracy
  0.9300 and CatBoost 0.9400. This verifies a smoke test only, not financial alpha
  or bitwise model reproducibility.
- Vendor integrity (11 files), snapshots (584 files), research references (41
  files), archived security classifications, inventory and core policy passed.
- Preflight: every gate G0–G6 remains blocked; no evidence was accepted.

Existing remote PR #79 checks passed at the original SHA:
[core](https://github.com/iitij/Gold-Intelligence-AI/actions/runs/42825719832),
[ML](https://github.com/iitij/Gold-Intelligence-AI/actions/runs/42825719420).
These runs do not establish CI success for subsequent commits.

## Changes and limits

CI now rejects source distributions and repeats the test/lint suite after a
fresh wheel installation without an index. The check creates a temporary
wheelhouse; it does not archive a durable, signed wheelhouse.

MT5 validation and feed analysis now share one in-memory byte snapshot. Previously
validation, parsing and revalidation reopened the file, leaving a race where
analyzed prices could differ from the hash in the report. A regression test
replaces the file after capture and verifies that reported prices and hash still
refer to the same snapshot. Memory now includes raw bytes and parsed rows;
streaming very large tick datasets is outside this M15 reader's scope.

## P02-02 decision: keep in_progress

Do not close #11. Remaining blockers:

1. Pin/review the installer and build bootstrap (pip/setuptools/wheel and embedded
   libraries), and run a fresh installed-environment SBOM/CVE scan. Local ensurepip
   also supplied setuptools 79.0.1, so the archived bootstrap findings cannot be
   declared fixed. Grype/Syft were unavailable locally; archived classification
   checks are not a fresh security scan.
2. pyproject build-system still permits floating setuptools>=69 and wheel.
   No locked package build or byte-identical wheel result was demonstrated.
3. Existing ML baseline excludes the full ml/agents extras, CUDA/Wine/MT5 and
   hardware evidence; Ubuntu CI is distinct from the local Debian result.
4. OS/Python patch, durable offline wheelhouse, current runtime SBOM and dependency
   license review still need recorded acceptance evidence.

## XAUUSD decision: training blocked

No original broker CSVs or official Bid/Ask reference files were present in this
workspace. The earlier figures (49,176 matched labels, 38 differences above USD 5,
10 nonoverlapping ranges) remain user-reported and were not reproduced here.
The historical HTTP 429 report was not retested and does not establish current
reference-service availability.

Before any training: acquire licensed original files and acquisition manifests
(provider, instrument/side, terms, retrieval time and SHA256); validate actual
schema; establish historical broker UTC/DST mapping independently; reconcile
M15 interval completeness and equivalent price sides; investigate discrepancies
against a documented reference; record contract specifications and historical
spread/commission/slippage/swap; then generate hashed datasets and leakage-safe
splits under the research protocol. Do not fill or delete disputed rows silently.
No raw data, training approval, task completion or live trading was introduced.

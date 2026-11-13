# Full CPU research environment — 2026-11-14

This follow-up resolves the missing **declared Python ml/agents CPU profile** in
audit 34. It does not resolve owner-machine, GPU/Wine/MT5, market-data or full
redistribution acceptance. P02-02 stays in_progress and G0–G6 remain blocked.

## Profile and change control

`requirements-research-cpu.lock` contains 123 exact packages with SHA256 hashes.
Combined with the build/bootstrap lock, it installs 128 distributions. It covers
all 11 direct dependencies in pyproject.toml's ml and agents extras. The resolver
was uv 0.13.6 with CPython 3.11.18 on Debian 13.6 Linux x86_64.

The one-time resolution command is recorded in the lock header. Existing
requirements-build.lock and requirements-ml-baseline.lock were used as constraints.
Neither those lockfiles nor requirements-ci.lock changed in this update. Shared
baseline versions were preserved. This profile is a review candidate; CI never
re-runs dependency resolution or updates versions automatically.

`verify_research_profile.py` checks declared extra ranges and shared versions;
--installed additionally requires the exact combined installed distribution set.
--evidence validates archived inventories, lock/report hashes and scan counts.

## Verified locally

- Hash-enforced wheel-only installation, pip check and exact installed-set check
  passed in a new CPython 3.11.18 environment.
- Downloaded 128 wheels (approximately 325 MiB) using both hash locks, then
  installed them into a second seedless venv with --no-index and --require-hashes.
  Exact installed-set, compatibility and full synthetic integration checks passed.
- Synthetic integration covers Parquet round-trip, Arrow-to-DuckDB SQL, four
  seeded Optuna trials, SQLite MLflow parameters/metrics/artifact storage, a
  local LangGraph state transition and a Pydantic NO_TRADE-only smoke contract.
- Existing synthetic LightGBM/CatBoost checks passed (accuracy 0.9300/0.9400).
- 195 repository tests and Ruff passed. Seven artifact-integrity tests reject
  corrupted/missing/stale files and wrong/dirty source revisions, and accept
  complete fixtures with a matching clean revision.

The smoke contract is a library integration check, not a deployed agent adapter
or trading capability. No vendor snapshots, market datasets, remote LLMs, model
weights, tracking server or broker clients are executed.

## Network finding and fix

The first smoke run blocked one Python network connection attempt from MLflow's
telemetry initialization. The guard initially raised an exception that the
library could suppress; counting attempts exposed that behavior. The final smoke
fails on *any* attempted connection, even if its exception was caught internally.

MLFLOW_DISABLE_TELEMETRY=true now applies before imports. LANGSMITH_TRACING and
LANGCHAIN_TRACING_V2 are false. Final runs, including the fresh offline install,
recorded zero attempts. These defaults are documented in .env.example; the
smoke applies them directly rather than assuming .env.example is loaded.

The guard patches Python socket.connect/connect_ex/create_connection. It is not
an OS network namespace or a proof against arbitrary native-code network calls.
MLflow uses a temporary SQLite database and explicit temporary file artifact URI;
no HTTP server or remote tracking endpoint is started.

## Fresh security and license evidence

Evidence is retained in
[research_cpu_2026_11_14](../planning/security/scans/research_cpu_2026_11_14/summary.json).
Syft 1.57.1 catalogued 517 components in the installed full profile, including
embedded components. Grype 0.121.3 reported zero matches and zero ignored matches,
with valid DB schema v6.1.10 built 2026-11-13T15:40:34Z. Exact tool archive hashes,
lock/report hashes, package inventories and local smoke logs are retained.
No custom advisory suppression or exclusion was introduced.

This scans discovered installed package content, not the OS, Python binary,
every native dependency, frozen vendor archive or a production deployment.
A zero-match snapshot does not establish absence of vulnerabilities.

License work now includes:

- Metadata for all 128 distributions and hashes/paths for 343 installed license,
  COPYING and NOTICE documents. This is an inventory, not a claim that every
  embedded component's distribution obligations have been accepted.
- Primary-term review of the 11 direct ml/agents packages. MIT texts resolve the
  incomplete Huey and skops metadata. Native bundles and additional notices remain
  distinct from the primary Python project license.
- CatBoost 1.2.10's primary Apache-2.0 text was missing from installed dist-info;
  the wheel has widget notices. A source-license supplement was fetched from
  matching release commit b1bd2a6d77219e82a1acfcedfccb8e6f6c1ee084.
- Flask-CORS 6.0.5 had no installed license document. Its MIT supplement was fetched
  from matching release commit 91ebc49c25aaf76b0e53e925feef1e3f19617c87.
  These source supplements do not independently attest wheel build provenance.
- MPL covered-file obligations (certifi/orjson/tqdm), bundled native terms/GCC
  runtime exceptions, and bundled JavaScript notices are identified for further
  redistribution review. There are 385 SBOM components without license metadata;
  they must not be treated as automatically licensed or approved.

Full redistribution/license acceptance remains open. See license_review.json;
no blanket legal or production approval is recorded.

## Retained wheelhouse and Ubuntu CI

The new research-cpu workflow uses Ubuntu 24.04 and Python 3.11. It downloads
hash-locked wheels, creates a manifest with source SHA, Python ABI/platform and
individual hashes, installs into a fresh venv **without an index**, checks exact
versions/compatibility, runs the guarded synthetic integrations and uploads the
wheelhouse only after success. Actions are commit-pinned; upload-artifact v7.0.2
uses cf430e030ddbb5b0abf93d22962f4752f3646cd9 (Node24).

The artifact includes the two locks, license metadata/document inventory/review,
the two supplemental license texts and offline instructions. It contains no raw
market data, credentials, experiment records or trained weights. Retention is
30 days, subject to GitHub repository limits; it is not permanent storage. The
artifact name includes the exact source SHA. The workflow then downloads that retained artifact using commit-pinned
download-artifact v8.0.2 (9000827ccba6bdab643e8b6fd33ac0654aef8333), fails on an
archive-digest mismatch, and rechecks every manifest entry plus the exact clean
source revision. Remote success and download links
must be verified at the current PR head, not inferred from earlier runs.

`verify_wheelhouse.py` rejects missing/extra files, symlinks and mismatched hashes.
A direct Cloud download of the first retained artifact returned HTTP 403 from
the storage endpoint; no claim of a successful Cloud download was made. The
runner round trip provides separate CI evidence, not owner-device evidence.
This verifies integrity against a manifest; authenticate the artifact separately
using the GitHub artifact digest and source revision. Downloading wheels and the
initial runner pip remain online trust prerequisites. The artifact does not
include an OS image, Python installer or GPU drivers. Native wheels remain
platform/ABI/glibc dependent; use the manifest and reproduce on the actual owner
machine before accepting it there.

## Concrete owner-machine evidence still needed

From a separate checkout at the artifact's source SHA, on the owner's Ubuntu
machine, unpack the artifact outside the checkout and use its absolute path:

```bash
GOLD_RESEARCH_WHEELHOUSE=/absolute/path/to/unpacked-artifact
python3.11 scripts/local_inventory.py --output .local/research_cpu_inventory.json
python3.11 scripts/verify_wheelhouse.py "$GOLD_RESEARCH_WHEELHOUSE" \
  --revision "$(git rev-parse HEAD)"
python3.11 -m venv --without-pip .local/research-cpu
python3.11 -m pip --python .local/research-cpu install --no-index \
  --find-links "$GOLD_RESEARCH_WHEELHOUSE" --require-hashes --only-binary=:all: \
  -r "$GOLD_RESEARCH_WHEELHOUSE/requirements-build.lock" \
  -r "$GOLD_RESEARCH_WHEELHOUSE/requirements-research-cpu.lock"
.local/research-cpu/bin/python -m pip check
.local/research-cpu/bin/python scripts/verify_research_profile.py --installed --evidence
.local/research-cpu/bin/python scripts/check_research_cpu.py
python3.11 scripts/preflight.py check training
```

The outer pip must support --python; the manifest records the tested interpreter
and platform. Preserve logs/inventory locally without account identifiers. Do not
run local_inventory.py on CI and relabel its output as owner-machine evidence.
The final training preflight must remain blocked until actual G0/G1 evidence is
reviewed. No owner-machine result was fabricated in this update.

## XAUUSD blocker unchanged

Original broker CSVs and official reference files are absent. Dataset source
rights/hashes, historical UTC/DST, contract/cost evidence, discrepancy resolution
and leakage-safe dataset/split manifests remain unverified. Follow the concrete
intake checklist in audit 34. No training dataset was created or accepted, no
real-data model trained and no live trading enabled. No task is marked done.

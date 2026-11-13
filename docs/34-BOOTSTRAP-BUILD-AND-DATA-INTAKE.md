# Bootstrap, core build and XAUUSD intake — 2026-11-14

This follow-up supersedes the bootstrap/build availability statements in audit
33; that earlier report remains a historical record. P02-02 stays in_progress,
PR #79 stays draft, and G0–G6 stay blocked. No raw-data acceptance or live trading.

## Deliberate dependency change

`requirements-build.in` explicitly selects pip 26.3, setuptools 84.2.1, wheel
0.48.0 and build 1.6.1. The separate SHA256 lock includes packaging 26.3 and
pyproject-hooks 1.3.3. It was generated once using uv 0.13.6 with CPython 3.11.18,
then installed with hash enforcement and binary wheels. This is an intentional
bootstrap update for the previous findings, not an automatic runtime upgrade.
The existing CI and ML-baseline lockfiles are unchanged.

`pyproject.toml` now pins the setuptools/wheel backend versions to the same
versions. CI and ML jobs create a venv without ensurepip, install the build lock
into it, then use that interpreter for subsequent installs/checks. This removes
the runner's seed setuptools and pip from the target package environment. The
runner's Python and pip still perform the initial installation and remain a
trust prerequisite; OS, interpreter and initial installer are not hash-locked.

`verify_ci_lock.py` checks backend consistency and locked bootstrap presence in
both workflows. A negative test rejects reintroduction of a floating backend.

## Build and reinstall evidence

On Debian 13.6 x86_64 / CPython 3.11.18:

- 188 tests and Ruff passed, including the new bootstrap drift and CSV preservation
  tests. CI-wheel reinstallation now also includes the bootstrap/build lock.
- Two separate copies of pyproject.toml and src produced byte-identical core
  wheels with SOURCE_DATE_EPOCH=315532800, no build isolation and PIP_NO_INDEX=1.
  SHA256: `90fa325e5e33582648ea8fb476c6596ef42bc92bb7c0465f809abd5d477a86dc`.
- The resulting wheel installed without dependencies or an index into a fresh
  venv and imported successfully with Python isolated mode (-I).
- This is a same-platform core wheel check, not an sdist, cross-platform, full
  ML/Agents, GPU, Wine, MT5 or complete offline machine reproduction claim.
- ML baseline plus the new bootstrap passed pip check and synthetic training:
  LightGBM 0.9300, CatBoost 0.9400. These are not market-performance estimates.

The [build record](../planning/security/scans/bootstrap_2026_11_14/core-wheel-build.json)
includes source-file hashes and tool versions. `check_package_build.py` produces
new evidence under ignored artifacts/ on each CI run. Remote results must be
read at the actual PR head; earlier successful checks do not cover this change.

## Fresh installed-environment security evidence

Syft 1.57.1 and Grype 0.121.3 were downloaded from official Anchore GitHub
releases and their archive SHA256s verified against the release checksums via
HTTPS. No signature verification claim is made. Exact tool archive hashes,
input lock hashes, package inventories and report hashes are in
[summary.json](../planning/security/scans/bootstrap_2026_11_14/summary.json).

| Installed profile | Syft components including embedded packages | Grype matches | Ignored matches |
| --- | ---: | ---: | ---: |
| build/bootstrap + CI | 109 | 0 | 0 |
| build/bootstrap + ML baseline | 170 | 0 | 0 |

Grype DB schema v6.1.10, built 2026-11-13T15:40:34Z, reported valid. Reports were
created on 14 November local client time. The old vulnerable embedded versions
were replaced: jaraco-context is now 6.1.0 and setuptools' embedded wheel is
0.46.3 (distinct from installed wheel 0.48.0). The archived November 8 reports
are preserved and still verified as historical evidence, not current findings.
No custom advisory suppression or exclude rule was added.

Zero matches is limited to these discovered installed-package components and
this database snapshot. It does not establish absence of vulnerabilities or
cover system libraries, the Python binary, frozen vendor archives, a full
Agents installation or every native dependency. SBOM license metadata is missing
for 86 CI and 129 ML components; dependency-license acceptance remains open.
`verify_bootstrap_evidence.py` verifies archive hashes, lock/inventory consistency,
DB metadata and summary counts. It is not a fresh online scan.

## Raw CSV preservation

The MT5 validator's --report previously used write_text and could overwrite its
source CSV or prior audit evidence. It now exclusively creates a new report and
returns exit code 2 if the destination already exists. Tests cover source paths,
symlinks, hardlinks, existing reports and successful new reports. Use a new report
filename on each audit. The feed comparator still writes only to stdout; shell
redirection must never target either input file.

## XAUUSD intake needed before training

Neither the two original broker CSVs nor official reference exports are present.
The earlier comparison totals therefore remain unreproduced, not accepted data.
Do not guess a reference CSV reader, UTC conversion or price scale.

| Evidence to acquire locally | Required verification |
| --- | --- |
| Unmodified broker M15 exports and export settings | SHA256, broker/server, symbol, closed-bar policy, timeframe, source/export time, original filename |
| Source terms and acquisition record | Provider URL, research-use rights, retrieval time in UTC, hash of original terms/evidence; no account identifiers in Git |
| Broker historical timing evidence | Server-to-UTC mapping for every effective/DST interval; independent dated evidence, not correlation alone |
| Contract snapshots and historical costs | Effective dates, contract/tick specifications, Bid/Ask convention, spread, commission, swap and slippage assumptions |
| Official independent Bid/Ask reference | Actual exported schema, units, instrument, timestamp basis, interval boundaries, completeness, terms and SHA256 |
| Discrepancy investigation | Align equivalent UTC instants/price sides; reproduce all unmatched/outlier reports; record explanations without silent deletions or filling |
| Derived training dataset | Parent hashes, reviewed transformations, available_at_utc, feature/label separation, purged chronological folds, locked holdout and trial ledger |

First local checks, once original files exist (replace symbol with the actual
exported broker symbol; raw files remain outside Git):

```bash
PYTHONPATH=src python -m goldintel.data.mt5_csv data/raw/mt5/broker_a.csv \
  --broker-symbol XAUUSD --report artifacts/broker_a_intake_001.json
PYTHONPATH=src python -m goldintel.data.compare_feeds \
  data/raw/mt5/broker_a.csv data/raw/mt5/broker_b.csv \
  --left-symbol XAUUSD --right-symbol XAUUSD
python scripts/preflight.py check training
```

The last check must remain blocked until reviewed evidence satisfies G0 and G1.
Passing the CSV validator produces a quality report with training_ready=false;
it cannot supply missing rights, timing, costs, reference data or approval.

## Remaining acceptance work

Full ML/Agents dependency and license review; owner-machine Ubuntu/hardware and
MT5/Wine/CUDA evidence where required; reproducible interpreter/OS and durable
offline wheelhouse; maintainer review of the new bootstrap lock; authenticated
real-data intake and UTC/cost investigation. No task was marked done in this update.

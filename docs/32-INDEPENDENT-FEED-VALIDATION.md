# Independent XAUUSD feed verification — 2026-11-10

## Evidence status

The original broker CSVs were found on the local workstation and the comparison
was independently reproduced on 2026-11-10. Each file contains 50,000 rows and
passes the strict MT5 schema, OHLC, numeric and timestamp ordering validator.
The result is 49,176 matching server labels, 38 close differences strictly above
USD 5 and 10 non-overlapping price ranges. Equal server labels do not establish
equal UTC instants. No original files were modified.

Local evidence (ignored, not published):
`artifacts/feed-audit-2026-11-10/broker-comparison.json`,
`investigation-windows.csv` and `reference-attempt.json` in the same directory.
The JSON comparison includes SHA256 fingerprints of both original CSVs.

A fresh request to the official Dukascopy datafeed for XAUUSD M1 Bid on
3 March 2026 returned HTTP 429. No reference payload was acquired or decoded.
The earlier export-widget attempt also had no confirmed downloadable result.
The HTTP error body is not treated as market data. The independent reference
comparison and historical UTC/DST verification remain pending.

Official entry point: https://www.dukascopy.com/swiss/english/marketwatch/historical/

## Reproducible broker comparison

`goldintel.data.compare_feeds` first invokes the existing strict MT5 validator.
Duplicates, invalid OHLC, invalid numeric fields and ordering errors fail before
matching. Reports include source SHA256, unmatched labels inside/outside the
shared date range, signed close differences, non-overlapping ranges, daily and
monthly counts, and consecutive outlier runs. The strict USD 5 threshold is a
diagnostic setting, not a rule that declares prices wrong. All readiness flags
remain false. No source is corrected, filled, or designated ground truth.

Example from repository root (set each symbol to the actual CSV broker_symbol):

```bash
PYTHONPATH=src python3 -m goldintel.data.compare_feeds \
  data/raw/mt5/gold_xauusd_m15.csv \
  data/raw/mt5/headway_xauusd_m15_20261110.csv \
  --left-symbol XAUUSD --right-symbol XAUUSD
```

Output goes to stdout only, so the command cannot overwrite input files.
Persist reports under ignored `artifacts/` when needed. Raw data stays outside Git.

## Remaining acceptance evidence

1. Receive official M1 Bid/Ask files for 2–11 March 2026 and record exact export
   settings, instrument, original filenames, retrieval time, terms and SHA256.
2. Validate the actual CSV schema before implementing a reference reader; never
   guess price scaling or use synthetic rows as a substitute for the download.
3. Establish historical server-to-UTC mapping separately for each broker and
   each DST interval. A correlation peak is supporting evidence, not proof.
4. Rebuild UTC M15 candles with explicit interval boundaries and report incomplete
   intervals rather than fill missing minutes. Compare equivalent price sides.
   M1 OHLC cannot recover intraminute spread or stop/target event ordering.
5. Broker-only reproduction is complete. Compare all three sources over aligned
   UTC intervals once the independent sample and time mapping are available,
   including 3 and 9 March. Investigate rather than delete discrepancies. Then
   review historical costs and readiness gates.

No training, trading, UTC conversion, or production approval follows from this change.

## Local verification — 2026-11-10

All 181 repository tests pass, including the five synthetic comparison tests;
Ruff passes for src, tests and scripts. These are software checks, not evidence
of trading performance or reference-data correctness.

The longest discrepancy groups reproduce the earlier investigation:

| Server-label interval | Candles | Mean MetaQuotes minus Headway close (USD) |
| --- | ---: | ---: |
| 2026-03-03 03:45–05:45 | 9 | +6.874444 |
| 2026-03-03 06:15–07:15 | 5 | +7.326000 |
| 2026-03-09 09:00–11:00 | 9 | +7.263333 |

Unmatched labels inside the shared range: 51 only in MetaQuotes and 730 only in
Headway. These are differences in observed labels, not established missing
trading bars; sessions, time mapping and source coverage still need verification.
Training and execution readiness remain false.

## Supplementary HistData acquisition and contract diagnosis — 2026-11-10

A real HistData March 2026 XAUUSD ASCII M1 Bid ZIP was downloaded successfully
(438,413 bytes; SHA256 24e4bd74637e3daa39467302ce788a50678f9bdd66d9603a94d16bb76fc26aca). Provenance is stored beside
the ignored raw ZIP. This is supplementary evidence: upstream independence and
licensing acceptance remain unverified. The documented schema specifies fixed
EST without DST: https://www.histdata.com/f-a-q/data-files-detailed-specification/ .
The new strict reader converts this fixed UTC-5 clock to UTC, validates OHLC and
ordering, and excludes incomplete M15 buckets. It found 30595 M1 rows,
2036 complete and 4 incomplete M15 buckets.

The local exploratory report compares March 3 and March 9 under explicit +2/+3
broker offset hypotheses. Neither is accepted as historical timezone evidence.
Under +2, median absolute close differences for MetaQuotes are USD 0.380/0.305;
for Headway USD 1.520/1.250. Samples have different coverage, broker historical
price side is unconfirmed, and upstream independence is unknown; these figures
do not determine broker correctness or approve training.

The contract diagnostic validates original snapshots and records observed tick
value ratios without assuming account/profit currency equivalence. MetaQuotes
reports tick value 0.1; Headway 1.0 with the same 100 contract size and 0.01 tick
size. Confirm account currency, conversions and calculation mode before sizing.
Snapshot offsets +7200 seconds establish neither historical offsets nor DST.

Local results: `artifacts/feed-audit-2026-11-10/REFERENCE-RESULTS-AR.md`,
`histdata-exploratory-comparison.json` and both `*-contract-check.json` reports.
Dukascopy's widget navigation failed with a connection reset. Its official S3
alternative requires AWS credentials and Requester Pays billing; no local AWS
credentials file was present and this path was not activated:
https://wiki.dukascopy.com/en/development/data-export .

## Further verification on the local workstation

`common.ini` in the active Wine installation names Headway-Demo. This is a
configuration observation, not a successful live API connection. terminal.ini's
USD setting belongs to the Tester section and is explicitly excluded from
account-currency evidence. Only selected metadata are stored in the ignored
`terminal-metadata-redacted.json` report; no account identifiers are collected.

`compare_reference_sample.py` reproduces the exploratory M1 comparison using the
same server labels for BOTH brokers and BOTH +2/+3 hypotheses on each day. This
removes coverage differences from the comparison. There are 88 labels per day.
Under +2, median absolute differences are MetaQuotes 0.385/0.305 USD and Headway
1.375/1.2365 USD on March 3/9. The previous unequal-sample statistics remain in
the original exploratory artifact for provenance; use `reference-common-cohort.json`
for this comparison. Matching still establishes neither independent provenance,
price-side equivalence nor historical server timezone correctness.

Official HistData FAQ documents Bid/Ask availability only in Generic ASCII ticks:
https://www.histdata.com/f-a-q/ . The new streaming tick-quality reader rejects
crossed/nonfinite prices and backwards timestamps, preserves equal-timestamp
observations, and calculates tick-weighted nearest-rank daily spread quantiles.
It does not substitute reference-feed spreads for broker execution costs.

Current published Headway Pro pricing mentions up to USD 1.5 per side per lot:
https://hw.online/accounts/pro/ . This current, tier-specific information cannot
establish the local demo tier or historical XAUUSD commissions. Swap documentation
also directs users to instrument specifications:
https://help.headway-online.care/hc/en-us/articles/10640320995357-Swap-Fee .
No historical costs have been certified from these pages.

Reproduce the common-cohort analysis from the project root:

```bash
PYTHONPATH=src .venv/bin/python scripts/compare_reference_sample.py \
  data/raw/reference/histdata/HISTDATA_COM_ASCII_XAUUSD_M1_202603.zip \
  data/raw/mt5/gold_xauusd_m15.csv \
  data/raw/mt5/headway_xauusd_m15_20261110.csv
```

Software verification: 195 tests pass; Ruff, the core safety check and repository
policy check pass. Training preflight remains BLOCKED for G0 and G1.

## Live metadata and real Bid/Ask download

The isolated local inspector subsequently connected to the running MT5 terminal
using the official MetaTrader5 Python package. It verified Headway-Demo,
account currency USD, demo trade mode 0, and current symbol chart mode 0 (Bid).
Current XAUUSD tick size is 0.01, contract size 100, profit/loss tick values 1 USD,
swap mode 1, long swap -41.8 and short swap 0. These are observations at the
report timestamp only. Standard/Cent/Pro pricing tier is still unknown.
The inspector stores only selected metadata, no account identities or balances.
The runtime is local and ignored; its Windows wheels were hash-checked against
PyPI release metadata. No project broker-order capability was introduced.

The HistData Generic ASCII tick ZIP for March 2026 was acquired (75,223,324 bytes;
SHA256 d3b8e84a1573243ed76411a49bbd88671523b08707f832bb1ec0df0ca1fda669).
It contains a 426,210,840-byte tick CSV and the provider's gap report. Provenance
and the original ZIP are under ignored data/raw/reference/histdata/.
The provider's separate status report was also downloaded. Provider gap summaries
are not substitutes for the local validation report.

A read-only Headway COPY_TICKS_ALL request for March 3, 02:45–03:15 UTC did not
return before the 55-second process limit. No historical broker ticks were
received; the March 9 request was not reached. A timeout does not establish
that the broker lacks those data. No account switching or trading occurred.
Live account metadata API documentation:
https://www.mql5.com/en/docs/python_metatrader5/mt5accountinfo_py .
Tick range/timezone contract:
https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksrange_py .

See ignored readiness-evidence.json for completed checks and remaining evidence.
Historical timezone, upstream independence and broker-specific historical costs
remain unresolved; no readiness gate has been accepted automatically.

## Tick validation completed

The entire acquired HistData ZIP passes the strict local reader: 9,471,352 ticks,
no crossed/nonfinite quotes and no backwards timestamps. Maximum observed gap
is 180,002,102 ms, including session/weekend gaps. UTC coverage is March 1
23:00:15.012 through April 1 04:59:59.905, because source months use fixed EST.
March 3 / March 9 UTC tick-weighted spread medians are 0.957 / 0.817 USD per ounce;
p95 values 1.887 / 1.180 and p99 values 2.717 / 1.524. The full daily report is
ignored `histdata-tick-quality.json`; these are not broker execution costs.
The current Arabic handoff is `artifacts/feed-audit-2026-11-10/CURRENT-VERIFICATION-AR.md`.

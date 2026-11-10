# Independent XAUUSD feed verification — 2026-11-10

## Evidence status

The two broker CSVs are on the user's workstation and are absent from this
checkout and the repository tree. The pasted audit results are user-reported,
not independently reproduced: 49,176 matched server labels, 38 close differences
strictly above USD 5, and 10 non-overlapping price ranges. Equal server labels
do not establish equal UTC instants.

Direct Dukascopy tick and M1 download attempts returned HTTP 429. The official
historical export widget was also used to request XAU/USD, 3 March 2026, M1,
UTC, both Bid and Ask. The dialog closed, but receipt of a downloadable file
could not be verified. No reference data has been acquired or validated.

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
5. Reproduce the broker comparison from the original files and compare all three
   sources over aligned UTC intervals, including 3 and 9 March. Investigate rather
   than delete discrepancies. Then review historical costs and readiness gates.

No training, trading, UTC conversion, or production approval follows from this change.

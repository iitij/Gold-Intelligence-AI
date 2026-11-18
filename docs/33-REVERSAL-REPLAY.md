# XAUUSD M15 reversal evaluation

The primary interval is 11 November 2026 00:00 UTC through 6 January 2027
00:00 UTC, exclusive. Record the Headway account tier, symbol, USD quote
currency, UTC mapping evidence, and commission schedule alongside the input.
The CSV columns are `timestamp_utc,bid,ask`, ordered by timestamp and then by
original source order for equal timestamps. Include two warm-up bars and
quotes through the end boundary. UTC is an input requirement.

Build M15 Bid closes from the last quote in each half-open interval. At the
next boundary, go short when the latest close rose and long otherwise,
including ties. Require two consecutive closes within 30 seconds of their
bar boundaries. Use the first quote at or after each order's scheduled time
within a 30-second wait. Exit at the next M15 boundary using the same rule.
Each signal represents one independent one-ounce trade. Buy at Ask and sell
at Bid. Subtract commission and configured slippage at both ends. Report
unobservable signals and missing fills, including periods when the market is
closed. Run delays of 0, 1 and 5 seconds.

The primary metric is mean net USD per ounce at zero delay and zero additional
slippage with observed spreads and documented commissions. Require at least
eight populated UTC weeks and a positive lower endpoint of the paired-in-time
weekly block bootstrap interval for a positive screening result. Review quote
coverage and the delay and slippage sensitivity before advancing. The CLI
accepts a different end for interim diagnostics, which are exploratory.

## Collection from MT5

Run the exporter on the machine running MT5 with the MetaTrader5 Python
package available and the intended Headway-Demo session open. Use a fresh
output file per daily request. For example, request the opening segment with:

```sh
python scripts/export_headway_ticks.py headway-20261111-raw.csv \
  --start 2026-11-10T23:25:00+00:00 --end 2026-11-11T00:10:00+00:00
```

Keep the returned `time_msc` values and record the requested bounds alongside
each file. Verify returned timestamp semantics against independently timed
observations before converting to the replay CSV's `timestamp_utc` column.
Extend collection through the primary end boundary and retain the warm-up
quotes. Record the actual commission in USD per side per ounce (divide a
documented USD per lot rate by the ounces per lot for that account).

## Interim Headway-Demo evidence

An aggregate local history query from 1–14 November 2026 found 210 XAUUSD
deal records. The commission, fee and swap fields were zero on every record.
The query found no separate account charge or commission entries among the
types checked. This supports zero explicit fees for the interim replay of
this demo account. Recheck the same account over the primary interval before
using the rate in the final report. The aggregate evidence is stored locally
at `artifacts/headway-cache-check.BL5qyk/fee-observation.json`.

The three-day replay used observed Bid/Ask prices and a provisional clock.
Its weekly confidence interval is unavailable because all fills fall in a
single week. The primary result requires the remaining quotes through
6 January 2027 and evidence that anchors the native timestamps to UTC.

## Reproduce the paired model diagnostic

From the repository root, use the locked CPU ML environment and run:

```sh
PYTHONPATH=src python scripts/reproduce_headway_november_diagnostic.py \
  artifacts/headway-cache-check.BL5qyk \
  data/raw/mt5/headway_xauusd_m15_20261110.csv \
  artifacts/headway-cache-check.BL5qyk/paired-model-recheck.json
```

The batch directory contains the November 11–13 native-clock exports and
the prior replay report that supplies the diagnostic interval. Choose a
fresh output path. The comparison uses identical opportunities across
models and delays and records the raw batch and training fingerprints.

For the scheduled reopening capture, read only records marked `changed_quote`
in the local `artifacts/headway-cache-check.BL5qyk/reopening-clock.jsonl`
log. Compare their `native_minus_host_seconds` values across several fresh
updates and record the host's NTP synchronization during the capture. The
initial cached quote has unknown age. A consistent offset anchors the
observed session only. Use separate evidence to cover earlier dates or a
clock transition.

## Prospective confirmation registered on 18 November

The opening portion of the original interval has already been inspected.
It cannot become an untouched holdout by waiting for its final date.
A separate prospective window, 23 November 2026 through 18 January 2027
exclusive, was registered before its start. See
`docs/37-PROSPECTIVE-HOLDOUT.md`. The repository replay rejects any interim
evaluation overlapping that sealed window, including the original interval
ending on 6 January. Data-quality collection may continue without strategy
performance inspection. All gate acceptance remains pending.

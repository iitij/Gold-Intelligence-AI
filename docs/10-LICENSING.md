# Source and model licensing decisions

## Confirmed license files at audited commits (2026-11-07)

- TradingAgents: Apache-2.0 (`LICENSE`).
- Aurum (zero-was-here/tradingbot): MIT (`LICENSE`).
- Midas: Apache-2.0 (`LICENSE`).
- Chronos forecasting code: Apache-2.0 (`LICENSE`).
- NeuralForecast code: Apache-2.0 (`LICENSE`).
- LightGBM: MIT (`LICENSE`).
- MooreSi/forex-gold and Nexus Trader: AGPL-3.0; **reference only**, not copied.
- Qwen **model weights**: license must be checked for the exact selected weight artifact, separately from GitHub repository code; do not assume general permissive rights.
- Data sources: broker/Dukascopy/FRED/CFTC/news each require terms review; public availability does not mean redistributable.

## Snapshot process

At first approved import, copy exact revision, top-level license and notices/NOTICE where present; save SHA and source URL; maintain original copyright and record local modifications in `vendor/SNAPSHOT_MANIFEST.json`. Do not copy extra source code beyond approved scope. Run license inventory and scan for embedded secrets. Internal changes must document provenance.

## License decision for OUR code

Not assigned. Keep repository private until an explicit license and commercial-use assessment. Do not add MIT/Apache automatically. No GPL/AGPL code imported into proprietary core without approved compatibility review.

This is an engineering checklist, not legal advice. License obligations are not removed by forking or vendoring a source snapshot.

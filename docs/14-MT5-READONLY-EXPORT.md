# P03-02 — Read-only XAUUSD MT5 M15 export

**Status:** MQL5 script and Python validator implemented and Python unit-tested. **MQL5 has NOT yet been compiled or run against your installed MT5 terminal.** No trades are executed, and no model is trained.

## Local workflow

1. In your MT5 terminal (including the Wine installation), inspect the exact broker symbol, e.g. XAUUSDm. Confirm it represents spot gold.
2. Open MetaEditor, create a Script in MQL5/Scripts, paste **mt5/ExportXAUUSD_M15.mq5**, and compile it.
3. Launch it on a gold chart, setting InpBrokerSymbol to the real symbol, and select an available history length. It uses CopyRates with shift 1 to exclude the currently forming candle.
4. Open the terminal Experts log, check the exported count, and find the CSV under the terminal COMMON DATA path, Files folder.
5. Copy the CSV locally to **data/raw/mt5/gold_xauusd_m15.csv**. Git ignores data/raw; never commit proprietary or personal market data.
6. Run the following read-only validator (substitute your exact broker symbol):

~~~bash
python -m pip install -e '.[dev]'
python -m goldintel.data.mt5_csv data/raw/mt5/gold_xauusd_m15.csv \
  --broker-symbol XAUUSDm --report data/validated/mt5_m15_report.json
~~~

## Scope and safety

- Schema: broker_symbol, timeframe (M15), server_time, OHLC, tick_volume, spread_points, real_volume.
- Validation: exact schema, symbol and timeframe; finite/positive prices; consistent OHLC; ordered, unique aligned bar times; nonnegative integer volumes/spreads. Session and weekend gaps are counted, never silently filled.
- The file reports SHA256 for audit and explicitly marks UTC and training and execution readiness FALSE.
- Broker-server timestamps are NOT assumed to be UTC. Before training or matching economic events, P03-01 and P03-04 must document the broker's historical time offsets and DST handling. A single current offset is insufficient evidence.
- This is not Tick Bid/Ask history or realistic execution simulation; spreads are in broker points. No account credentials, account IDs, orders or trade API are used.
- MQL5 compilation and broker feed validation remain explicit acceptance steps; passing Python validation is not certification of trading readiness.

See issues P03-01, P03-02 and P03-04. No live execution path exists.

## مواصفات الوسيط: Script إضافي للقراءة فقط

شغّل [ExportXAUUSD_SymbolSpec.mq5](../mt5/ExportXAUUSD_SymbolSpec.mq5) لاستخراج عقد الذهب الحالي دون بيانات الحساب أو إرسال أوامر. ثم استخدم [فاحص المواصفات المستقل](26-BROKER-CONTRACT-INTAKE.md). لا تتعامل مع فرق الساعة الحالي باعتباره إثباتًا تاريخيًا لـDST أو UTC.

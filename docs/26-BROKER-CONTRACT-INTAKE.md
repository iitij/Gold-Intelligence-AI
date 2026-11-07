# عقد مواصفات وسيط الذهب — قراءة فقط

**الفائدة:** ملف فحص قابل للمراجعة يثبت كيف ظهر رمز الذهب في منصة MT5 لدى الوسيط لحظة التجميع، دون قراءة حساب المستخدم أو فتح/إغلاق الصفقات.

## الخطوات على جهازك
1. افتح `MetaEditor` تحت MT5 في Ubuntu/Wine، وأنشئ Script باسم `ExportXAUUSD_SymbolSpec.mq5` من [الكود](../mt5/ExportXAUUSD_SymbolSpec.mq5)، واجمعه وتحقق من رسائل المترجم.
2. اختر رمز الذهب الفعلي مثل `XAUUSD` أو `XAUUSDm`، وشغّل Script للقراءة فقط.
3. احفظ ملف `gold_xauusd_symbol_spec.csv` من مجلد البيانات المشترك في `data/raw/mt5/` محليًا. لا تدفع CSV إلى GitHub دون فحص حقوق وسيطك.
4. نفذ:

```bash
python -m goldintel.data.broker_specs \
  data/raw/mt5/gold_xauusd_symbol_spec.csv \
  --broker-symbol XAUUSDm \
  --report data/validated/broker_symbol_report.json
```

استبدل الرمز بالاسم الحقيقي المعروض من الوسيط. احتفظ بالتقرير محليًا، وشارك النتائج غير الحساسة فقط إذا رغبت.

## بيانات نعتمدها كبداية

`point` و`tick_size` و`tick_value_profit/loss` و`contract_size` و`volume_min/max/step` و`stops/freeze levels` و`currency_profit` و`trade_calc_mode` و`trade_execution_mode`، مع زمن التقاط المراجعة ومقدار فرق الساعة *الملحوظ*.

## قيود صارمة

- فرق `TimeTradeServer()-TimeGMT()` **ملاحظ/مقدر فقط**؛ `TimeTradeServer()` يحسب داخل عميل MT5 ويتأثر بساعة الجهاز، و`TimeGMT()` يعتمد أيضًا على توقيت وDST المحلي. لا تستنتج منه قاعدة DST تاريخية أو `available_at_utc` للشموع السابقة. مراجع MetaQuotes: [TimeTradeServer](https://www.mql5.com/en/docs/dateandtime/timetradeserver) و[TimeGMT](https://www.mql5.com/en/docs/dateandtime/timegmt).
- هذا التقرير لا يثبت القيمة النقدية الفعلية للخسارة بعملة الحساب، ولا سيولة التنفيذ، ولا عقود وسيط تاريخية. `broker_order_check_ok` لا يُضبط من هذا الملف.
- يحتفظ التقرير ب`training_ready=false` و`execution_ready=false` دائمًا. يحتاج التحضير بيانات Bid/Ask/Tick وصحة UTC/DST وحقوق الاستخدام وبيانات سوق مستقلة.
- لا نقرأ `AccountInfo*` أو الحساب أو الأرباح أو مراكز التداول، ولا توجد دالة `OrderSend` في Script.
- هذا الكود لم يُختبر في MetaEditor بعد؛ اختبارات Python فقط تتحقق من بنية بيانات اصطناعية.

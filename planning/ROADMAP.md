# خارطة الطريق / Roadmap (XAUUSD only)

**حالة المشروع:** تأسيس بحثي، لا نموذج مُدرب ولا ربط تداول حي. هذه الخطة قابلة للتمدد ولا تفرض تاريخ إطلاق أو ربحية متوقعة.

## How to extend

- `planning/backlog.json` هو مصدر الحقيقة للمهام. IDs لا يعاد استخدامها؛ المرحلة التالية يمكن أن تكون P11.
- أضف مهمة مع شروط قبول وتبعيات وعلامات واضحة؛ اعتمد تغييرها في Pull Request.
- تستخدم Issues للمتابعة، بينما يظل backlog في Git قابلًا للمراجعة وإعادة الإنتاج.
- لا تُرقّى أي مرحلة إلى الإنتاج تلقائيًا؛ وثيقة Production Gates هي المرجع.

## Phases and dependencies

### P00 — الحوكمة والتأسيس
Governance and repository bootstrap · 4 tasks

- **P00-01** إقرار نطاق XAUUSD ومعايير النجاح — `start`
- **P00-02** إنشاء المستودع الخاص وحماية الفرع — `P00-01`
- **P00-03** استيراد المهام والقوالب — `P00-02`
- **P00-04** سجل ADR وإدارة التغيير — `P00-01`

### P01 — تجميد المصادر وتدقيق التراخيص
Fixed source import and provenance · 5 tasks

- **P01-01** مراجعة تراخيص المصادر وأوزان النماذج — `P00-01`
- **P01-02** استيراد Aurum المثبت — `P01-01`
- **P01-03** استيراد TradingAgents المثبت — `P01-01`
- **P01-04** تقييم استيراد مكونات Midas — `P01-01`
- **P01-05** إعداد SBOM وفحص المكونات — `P01-02, P01-03`

### P02 — بيئة التطوير والتشغيل
Local development and infrastructure · 3 tasks

- **P02-01** فحص عتاد Ubuntu وWine وMT5 — `P00-01`
- **P02-02** بيئة بناء وإعادة إنتاج — `P02-01`
- **P02-03** اختيار التخزين وتنظيم المشاريع — `P02-02`

### P03 — بيانات XAUUSD وإدارتها
Market and macro data platform · 6 tasks

- **P03-01** تعريف مواصفات رمز الذهب لدى الوسيط — `P02-01`
- **P03-02** تصدير OHLC وTick من MT5 بأمان — `P03-01`
- **P03-03** استيراد بيانات Dukascopy التاريخية — `P01-02, P03-01`
- **P03-04** التحقق من OHLC/Quotes/Fills — `P03-02, P03-03`
- **P03-05** انضمام البيانات الاقتصادية زمنيًا — `P03-04`
- **P03-06** واجهة MarketSnapshot ذات نسخ — `P03-04, P03-05`

### P04 — الخصائص والتوسيم
Feature engineering and supervised labels · 3 tasks

- **P04-01** خصائص أسعار وزخم وتقلبات متزامنة — `P03-04`
- **P04-02** Triple-Barrier وmeta-labeling — `P04-01`
- **P04-03** مخازن عينات ومجموعات زمنية — `P04-02`

### P05 — التجارب الكمية الأساسية
Quantitative baseline models · 5 tasks

- **P05-01** خطوط أساس بسيطة قبل ML — `P04-03`
- **P05-02** تدريب LightGBM على XAUUSD — `P05-01`
- **P05-03** تدريب CatBoost على الذهب — `P05-02`
- **P05-04** معايرة وتحديد امتناع NO_TRADE — `P05-03`
- **P05-05** سجل النماذج والتوقيع — `P05-02`

### P06 — التنبؤات الزمنية
Time-series foundation models · 3 tasks

- **P06-01** مقارنة Chronos-2 Zero-shot — `P05-02`
- **P06-02** تخصيص Chronos-2 فقط إن أضاف قيمة — `P06-01`
- **P06-03** مقارنة NHITS/NBEATSx — `P06-01`

### P07 — وكلاء LLM المحليون
Local agent orchestration and model customization · 5 tasks

- **P07-01** تكامل TradingAgents مع Gold Tools — `P01-03, P03-06`
- **P07-02** تشغيل Ollama المحلي وتقييم Qwen — `P02-01, P07-01`
- **P07-03** مجلس وكلاء الذهب متعدد الأدوار — `P07-02, P05-04`
- **P07-04** مجموعة SFT محكمة لـ Qwen — `P07-03`
- **P07-05** LoRA/QLoRA وتقييم Qwen المخصص — `P07-04`

### P08 — الاختبار والتقييم
Backtesting and rigorous validation · 4 tasks

- **P08-01** محاكاة تنفيذ ذهب واقعية — `P03-06, P04-02`
- **P08-02** Walk-Forward + Purging + Holdout — `P08-01, P05-04`
- **P08-03** اختبارات ضغط وتقلبات 2020–2026 — `P08-02`
- **P08-04** بوابة قبول أفضلية إحصائية — `P08-03`

### P09 — الربط والتنفيذ التجريبي
MT5 integration, paper and demo execution · 5 tasks

- **P09-01** بناء جسر MQL5 لقراءة السوق — `P03-01, P02-02`
- **P09-02** بوابة المخاطر المستقلة — `P09-01, P08-01`
- **P09-03** تداول ورقي منفصل عن حساب MT5 — `P09-02, P08-04`
- **P09-04** حساب تجريبي MT5 بموافقة بشرية — `P09-03`
- **P09-05** اختبار استقرار طويل وتشغيل 24/5 — `P09-04`

### P10 — الأمان والمراقبة والجاهزية
Security, observability and production gates · 5 tasks

- **P10-01** مراقبة النظام والإنذارات — `P09-03`
- **P10-02** إدارة الأسرار والنسخ الاحتياطية — `P02-02`
- **P10-03** سلسلة نشر قابلة للتراجع — `P09-05, P10-01, P10-02`
- **P10-04** تقييم الإنتاج النهائي دون تفعيل حي — `P10-03, P08-04`
- **P10-05** بحث RL فقط عند سلامة المحاكي — `P08-04, P09-03`

## Initial critical path

`P00-01 → P00-02 → P01-01 → P01-02/P01-03 → P03-01...P03-06 → P04-01...P04-03 → P05-01...P05-04 → P08-01...P08-04 → P09-01...P09-05 → P10-04`

## Explicitly deferred

- Live trading remains disabled in code; a later separate ADR and safety review would be required even to propose adding a live path.
- RL stays a research-only optional stream (`P10-05`) with no production authorization.
- Source packages are frozen at first reviewed import; no future upstream sync.

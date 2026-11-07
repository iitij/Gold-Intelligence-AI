# Gold Intelligence AI — XAUUSD Only

> **Status:** research bootstrap / paper-only / **NO LIVE TRADING**. No demonstrated trading edge or validated deployed model yet.
>
> **Language:** العربية هي لغة التوثيق الرئيسية. Code, interfaces and machine-readable specifications use English.

مشروع بحث وتطوير محلي لتدريب نماذج متخصصة في الذهب **XAUUSD فقط**، مع تنسيق وكلاء محليين ومراقبة تداول تجريبي عبر MT5. يدمج أفكارًا وأطرًا مفتوحة المصدر مع نظام تدريب وتقييم نملكه ونصونه داخليًا.

[مركز جميع المصادر والنماذج](docs/16-SOURCE-HUB.md) · [أساس الخصائص السببية والتوسيم](docs/20-POINT-IN-TIME-FOUNDATION.md) · [تقرير استلام تجهيزات ما قبل البحث](docs/28-PRE-RESEARCH-READINESS-STATUS.md) · [تجهيزات ما قبل البحث](docs/24-PREFLIGHT-RUNBOOK.md) · [التدقيق الشامل ودرجة النضج](docs/23-COMPREHENSIVE-MATURITY-AUDIT.md) · [البحث الإضافي ومصادر التسريع](docs/21-OPEN-SOURCE-ACCELERATION-RESEARCH.md) · [التدقيق الشامل والفجوات](docs/17-INDEPENDENT-TECHNICAL-AUDIT.md) · [حالة النشر الحالية](docs/13-STATUS.md) · [المهام الفعلية على GitHub](https://github.com/iitij/Gold-Intelligence-AI/issues)

## الوثيقة المرجعية / Single source of truth

- [ميثاق المشروع](docs/00-CHARTER.md)
- [المعمارية والعقود](docs/01-ARCHITECTURE.md)
- [سجل مصادر GitHub الثابت](sources/README.md) و [`sources.lock.json`](sources/sources.lock.json)
- [قرارات التصميم ADR](docs/adr/0001-frozen-upstream.md)
- [البيانات وحوكمة الحقوق](docs/02-DATA-GOVERNANCE.md)
- [خطة النماذج والتدريب](docs/03-TRAINING-STRATEGY.md)
- [بروتوكول البحث والاختبار](docs/04-RESEARCH-PROTOCOL.md)
- [استراتيجيات البحث](docs/05-STRATEGIES.md)
- [مجلس الوكلاء المحلي](docs/06-AGENTS.md)
- [المخاطر وتنفيذ MT5](docs/07-RISK-EXECUTION.md)
- [الأمن والإنتاج](docs/08-SECURITY-OPERATIONS.md)
- [معايير الجاهزية للإنتاج](docs/09-PRODUCTION-GATES.md)
- [التراخيص ومصدر المكونات](docs/10-LICENSING.md)
- [خطة التنفيذ المتوسعة](planning/ROADMAP.md) و [`planning/backlog.json`](planning/backlog.json) و [`planning/backlog.csv`](planning/backlog.csv)
- [سجل القرارات المفتوحة](docs/11-OPEN-DECISIONS.md)
- [دليل تصدير XAUUSD من MT5 للقراءة فقط](docs/14-MT5-READONLY-EXPORT.md)
- [تدقيق سلامة وحدات Aurum وTradingAgents المجمدة](docs/15-VENDOR-INTEGRITY.md)

## المبدأ الثابت

**لا نتابع تحديثات مشاريع المنبع بعد تجميد النسخة.** يحتفظ المشروع بمراجعات ثابتة ذات SHA ومعاينة المصدر والترخيص واختبارات توافق داخلية. لا `git submodule update --remote`، ولا `pip install -U` عشوائيًا على النظام الإنتاجي. يسمح باستيراد أولي من مراجعات مثبتة فقط مع مراجعة أمنية وترخيصية؛ بعد ذلك تُجرى الإصلاحات داخل مستودعنا مع توثيق أسبابها. تفاصيل: [ADR-0001](docs/adr/0001-frozen-upstream.md).

**حالة المصدر:** يحتوي المستودع على وحدات مختارة من Aurum وTradingAgents، بالإضافة إلى النسخ الكاملة المجمدة من Aurum وTradingAgents وMidas في `vendor/snapshots/` مع تراخيصها وبصمات SHA256. لا يحتوي على أوزان نماذج أو بيانات وسطاء. جُهز سكريبت استيراد أولي وحيد من Commit SHA ثم تتولى صيانة الكود داخليًا، دون تحديثات تلقائية. اكتمل الاستيراد الأولي إلى الأرشيف الثابت ولا تعاد مزامنة المصدر بعد ذلك. لا تعتمد خدماتنا على المنبع وقت التشغيل.

## Quick start (local only)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
python scripts/verify_vendor_integrity.py
python -m goldintel health
python -m goldintel sample-risk
```

أضفنا سكريبت تصدير CSV للشموع المغلقة من داخل MT5؛ لم يتم بعد تجميعه على جهاز المستخدم أو استلام بيانات الوسيط. فحص CSV محلي وغير متصل بالوسيط. لا يوجد أي تنفيذ لأوامر حقيقية. **بوابة التنفيذ الحي غير مطبّقة ومعطلة تصميميًا.**

## Read-only XAUUSD data intake

اتبع [دليل MT5](docs/14-MT5-READONLY-EXPORT.md) و[استخراج مواصفات عقد الوسيط](docs/26-BROKER-CONTRACT-INTAKE.md) لاستخراج شموع M15 المغلقة، ثم افحص CSV محليًا باستخدام الأمر التالي، مع استبدال اسم الرمز باسم الوسيط الصحيح:

```bash
python -m goldintel.data.mt5_csv data/raw/mt5/gold_xauusd_m15.csv \
  --broker-symbol XAUUSDm --report data/validated/mt5_m15_report.json
```

نجاح الفحص لا يعني أن توقيت الوسيط تحول إلى UTC أو أن البيانات صالحة للتدريب؛ يجب تنفيذ بوابات حوكمة التوقيت والحقوق أولًا.

## First source freeze (one time, never automatically)

```bash
python scripts/freeze_sources.py --dry-run
# after legal/security review, on an internet-connected workstation:
python scripts/freeze_sources.py --confirm
```

نُفذ الاستيراد الأولي المجمد من مراجعات ثابتة وأُدرج في `vendor/snapshots/`. البرنامج الأصلي للمرجعية فقط ولا يعاد تشغيله لتحديث المنبع. لا ينفذ أي تحديث بعد ذلك. يرفض الكتابة فوق نسخة موجودة.

## GitHub publication

راجع [`docs/12-PUBLISHING.md`](docs/12-PUBLISHING.md). نوصي بمستودع خاص أولًا. المستودع الخاص `iitij/Gold-Intelligence-AI` قائم وبه 52 Issue موزعة على 12 مرحلة. استخدم `bash scripts/bootstrap_publish.sh` لفحوص النشر فقط؛ أداة `scripts/publish_issues.py` تحقق التزامن دون نسخ المهام الموجودة. لا تحفظ أي بيانات حساب أو ملفات أسرار في Git.

## Licensing

لم يتم بعد اختيار ترخيص لهذا المشروع الأصلي؛ قرار النشر والترخيص مؤجل. يحتفظ كل مصدر خارجي بحقوقه وترخيصه. **لا تُدمج ملفات AGPL في النواة** قبل مراجعة قانونية منفصلة. أوزان Qwen وChronos والبيانات التاريخية لها شروط مستقلة.
## Single source / model hub

راجع [مركز المصادر والنماذج](docs/16-SOURCE-HUB.md) لسجل المشاريع الإحدى عشرة، والمستودعات الثلاثة المرخصة المرشحة للاستيراد الكامل، وخطة تجميد النماذج Qwen/Chronos وتخزين أوزانها محليًا. [ملف المرشحين](models/foundation_candidates.json). لا يشمل هذا المستودع أوزانًا مدربة أو بيانات سوق. تم اعتماد النسخ المجمدة في `vendor/snapshots/` داخل `main` وملف `vendor/SNAPSHOT_MANIFEST.json`، لكن لم تصبح حزمًا إنتاجية أو مدربة.

**التحقق من النقل الكامل:** `python scripts/verify_full_snapshots.py` يفحص جميع الملفات المجمدة وبصماتها، وSHA لنماذج Qwen وChronos. [الوثيقة الموحدة](docs/16-SOURCE-HUB.md). لا تُشغّل شيفرات المنبع مباشرة دون فحص الاعتماديات الأمني واختبارات التكامل.

## تدقيق النواة البحثية وتحسين المخاطر

- [التدقيق الهندسي والعلمي](docs/17-INDEPENDENT-TECHNICAL-AUDIT.md) وسجل الفجوات.
- [مراجعة مخاطر Paper-only](docs/18-RISK-GATE-REVIEW.md) توثق إصلاح شبكة أحجام اللوت والقيود المتبقية.
- [P11 مسارات بحث متقدمة](planning/ROADMAP.md): المنافسة البحثية، بنية سوق الذهب، تقييم Champion/Challenger ومرصد تكاليف الوسيط.

## New third-party candidate research — no runtime dependency

The [2026-11-08 open-source acceleration review](docs/21-OPEN-SOURCE-ACCELERATION-RESEARCH.md) and [exact-commit candidate lock](sources/research_candidates_2026_11_08.lock.json) identify 10 additional projects. Pandera/MLForecast are candidate *future pinned dependencies*, not installed in the operational core. Only two small reference repositories may be snapshotted for **offline code review** in `vendor/research_refs/`, with no import, test execution, broker connectivity or upstream auto-sync. Trading remains paper-only.

## Pre-research readiness (default: BLOCKED)

Run `python scripts/preflight.py status` and `python scripts/preflight.py check training`. The latter is expected to **block** until G0/G1 are independently evidenced and accepted. The readiness manifest is not an execution switch. For local workstation sizing, run `python scripts/local_inventory.py --output .local/hardware_inventory.json` on Ubuntu; `.local/` stays ignored by Git. [Runbook](docs/24-PREFLIGHT-RUNBOOK.md).

## Deterministic test bootstrap (Python 3.11 CI only)

CI uses [SHA256-pinned test requirements](requirements-ci.lock) and [immutable checkout/setup-python actions](.github/workflows/ci.yml), rather than floating extras. Run `python scripts/verify_ci_lock.py` to check the policy. This is **not a full ML/GPU runtime lock or a security audit**. [Supply-chain plan](docs/25-CI-REPRODUCIBILITY.md).

### Broker contract snapshot (no account access)

Run the read-only [XAUUSD symbol specification script](mt5/ExportXAUUSD_SymbolSpec.mq5) inside MetaEditor; it exports tick size, point, lot rules, profit currency, current contract size and observed (unverified) clock offset. Validate it with `python -m goldintel.data.broker_specs ...`. **It never determines historic DST or authorizes training/trading**. [Full instructions](docs/26-BROKER-CONTRACT-INTAKE.md).

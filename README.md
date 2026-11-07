# Gold Intelligence AI — XAUUSD Only

> **Status:** research bootstrap / paper-only / **NO LIVE TRADING**. No demonstrated trading edge or validated deployed model yet.
>
> **Language:** العربية هي لغة التوثيق الرئيسية. Code, interfaces and machine-readable specifications use English.

مشروع بحث وتطوير محلي لتدريب نماذج متخصصة في الذهب **XAUUSD فقط**، مع تنسيق وكلاء محليين ومراقبة تداول تجريبي عبر MT5. يدمج أفكارًا وأطرًا مفتوحة المصدر مع نظام تدريب وتقييم نملكه ونصونه داخليًا.

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

## المبدأ الثابت

**لا نتابع تحديثات مشاريع المنبع بعد تجميد النسخة.** يحتفظ المشروع بمراجعات ثابتة ذات SHA ومعاينة المصدر والترخيص واختبارات توافق داخلية. لا `git submodule update --remote`، ولا `pip install -U` عشوائيًا على النظام الإنتاجي. يسمح باستيراد أولي من مراجعات مثبتة فقط مع مراجعة أمنية وترخيصية؛ بعد ذلك تُجرى الإصلاحات داخل مستودعنا مع توثيق أسبابها. تفاصيل: [ADR-0001](docs/adr/0001-frozen-upstream.md).

**تنبيه:** هذا الملف المضغوط يحتوي على الهيكل والكود الأصلي الذي أنشأناه وملفات تثبيت المصادر؛ **لا يحتوي حاليًا على نسخ كاملة من المشاريع الخارجية أو أوزان نماذج أو بيانات وسطاء**. يجب إجراء التجميد الأولي من آلة متصلة بالإنترنت بعد تدقيق المصادر والحقوق. لا تعتمد خدماتنا على المنبع وقت التشغيل.

## Quick start (local only)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
python -m goldintel health
python -m goldintel sample-risk
```

لا يوجد في النسخة الحالية أي اتصال ببروكر أو مفاتيح API أو تنفيذ أوامر حقيقية. **بوابة التنفيذ الحي غير مطبّقة ومعطلة تصميميًا.**

## First source freeze (one time, never automatically)

```bash
python scripts/freeze_sources.py --dry-run
# after legal/security review, on an internet-connected workstation:
python scripts/freeze_sources.py --confirm
```

البرنامج يتحقق من SHA، وينسخ المصدر إلى `vendor/snapshots/` مع الاحتفاظ بملفات التراخيص. لا ينفذ أي تحديث بعد ذلك. يرفض الكتابة فوق نسخة موجودة.

## GitHub publication

راجع [`docs/12-PUBLISHING.md`](docs/12-PUBLISHING.md). نوصي بمستودع خاص أولًا. استخدم `bash scripts/bootstrap_publish.sh iitij/Gold-Intelligence-AI` على محطة لديها GitHub CLI ومصادقة الحساب الصحيح، أو أنشئ مستودعًا خاصًا فارغًا يدويًا ثم ادفع الكود. استورد **48 مهمة موزعة على 11 مرحلة** بواسطة `scripts/publish_issues.py` بعد إنشاء المستودع. لا تحفظ أي بيانات حساب أو ملفات أسرار في Git.

## Licensing

لم يتم بعد اختيار ترخيص لهذا المشروع الأصلي؛ قرار النشر والترخيص مؤجل. يحتفظ كل مصدر خارجي بحقوقه وترخيصه. **لا تُدمج ملفات AGPL في النواة** قبل مراجعة قانونية منفصلة. أوزان Qwen وChronos والبيانات التاريخية لها شروط مستقلة.

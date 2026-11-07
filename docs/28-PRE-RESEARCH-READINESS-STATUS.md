# تقرير تسليم تجهيزات ما قبل البحث الفعلي — 2026-11-08

**النطاق:** GitHub/CI والأمان الأولي والحوكمة والعقود وMT5 read-only. **النتيجة ليست قبول G0 أو G1 أو إذن تداول**.

## تم التحقق داخل GitHub

- GitHub repo خاص، 52 Issue قائمة، **جميعها تحمل Labels صحيحة** حسب `planning/backlog.json`، وكل واحدة مرتبطة بإحدى 12 Milestone فعلية.
- بعد توثيق PRs جزئية: **37 todo، 12 in_progress، 2 review، 1 blocked**؛ لا مهمة `done` قبل تحقق قبولها.
- GitHub Actions تستخدم checkout v5 وsetup-python v6 مثبتين Git SHA، مع Python 3.11 وحزم dev/test في `requirements-ci.lock` بإصدارات وSHA256.
- تم اختبار بوابات قبول G0..G6، وهي **محجوبة افتراضيًا**. `scripts/preflight.py check training` يرجع BLOCKED حتى اكتمال الدليل المطلوب.
- `scripts/local_inventory.py` يولد تقرير مواصفات عتاد دون جمع هوية حساب أو مستخدم؛ خرجه في `.local/` المُستثنى من Git.
- `mt5/ExportXAUUSD_M15.mq5` و`mt5/ExportXAUUSD_SymbolSpec.mq5` للقراءة فقط، واثنان من فاحصي Python يرفضان بيانات غير صالحة. **لم تُجمع أو تُجرّب هذه السكريبتات في MT5 الحقيقي**.
- جميع الشيفرات الخارجية المؤرشفة محفوظة عند مراجعات ثابتة. أرشيف المراجع البحثية خارج المسار التنفيذي.
- أزلنا الإجراءات المؤقتة ذات صلاحيات الكتابة بعد اكتمال نقل المصادر وإنشاء Milestones.

## ما لم ننته منه — blockers حقيقية

**G0:** `main.protected=false`، وخطة GitHub للمستودع الخاص قيّدت Rulesets. سياسة PR الحالية تنظيمية وليست إنفاذًا تقنيًا؛ لا نغير خصوصية المستودع. كما يلزم SBOM/CVE وlicense triage كامل، وقفل اعتمادات `ml` و`agents` ومنصة OS/Driver. [المخزون المبدئي](../planning/security/component_inventory.json) **ليس SBOM مكتملًا ولا تقرير فحص ثغرات**.

**G1:** لن يتم قبول أي Dataset إلا بعد تشغيل السكريبتات فعليًا على جهاز المالك، جمع عينات Bid/Ask/Tick من وسيط مرخص، تأكيد التوقيت التاريخي UTC/DST، جودة البيانات، ومواصفات العقد. لا يمكننا الوصول إلى جهاز المستخدم أو حساب MT5 من خلال GitHub.

**G2..G6:** لا توجد نماذج LightGBM/CatBoost مدربة على بيانات حقيقية، أو تقرير Walk-Forward مالي يخص المشروع، أو Bridge Demo، أو تشغيل Qwen وChronos، أو اختبارات أعطال طويلة. ولا يوجد أي تفعيل Live.

## أوامر المتابعة المختصرة على جهاز Ubuntu

```bash
git clone https://github.com/iitij/Gold-Intelligence-AI.git
cd Gold-Intelligence-AI
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-ci.lock
PYTHONPATH=src python -m pytest -q
python scripts/preflight.py status
python scripts/preflight.py check training      # expected: BLOCKED, exit 2
python scripts/local_inventory.py --output .local/hardware_inventory.json
```

ملف CSV المستخرج من MT5 يجب وضعه فقط في المسار المحلي المستثنى من Git. [التصدير](14-MT5-READONLY-EXPORT.md) و[مواصفات العقد](26-BROKER-CONTRACT-INTAKE.md).

## قرار الاستعداد

**اكتمال تجهيزات GitHub الأساسية ≠ جاهزية بدء التدريب**. المرحلة التالية بعد هذه التجهيزات هي إثبات البيئة المحلية + مواصفات وسيط XAUUSD + جودة بيانات السوق. لا نتعجل تنزيل أوزان Qwen أو دمج روبوتات جديدة قبل أول نموذج كمي موثق النتائج.

هذه الوثيقة سجل وضع مؤرخ وليست شهادة ضمان أمن أو أفضلية تداول.

## إضافات الأمن بعد تقرير الاستلام

أُنجز فحص مؤرخ بـSyft/Grype [#42422206182](https://github.com/iitij/Gold-Intelligence-AI/actions/runs/42422206182) وصُنفت المطابقات حسب مواقعها؛ 10 تخص CI Bootstrap و146 تخص قفل اعتمادات Midas المؤرشف. لا يزال علاج التحذيرات وتدقيق الاعتماديات الكامل وحماية main مطلوبة. لا تتغير بوابة G0 من blocked. [النتائج المفصلة](31-SBOM-TRIAGE-2026-11-08.md).

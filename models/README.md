# Research model registry — XAUUSD only

**ابدأ من [مركز النماذج الموحد](MODEL-HUB.md)** للاطلاع على جميع المرشحين، والمراجعات الثابتة، وحالة الأوزان ومكان تخزينها. هذا هو مدخل المستخدم الواحد للمصادر؛ لكنه لا يعني وجود ملفات أوزان فعلية في Git.

## السجلات القابلة للقراءة آليًا

- [foundation_candidates.json](foundation_candidates.json) — قائمة النماذج الجاهزة والمرشحين للتدريب، ومنها NBEATSx.
- [foundation_weights.lock.json](foundation_weights.lock.json) — **موجود على `main`**؛ يثبت 3 مراجعات Hugging Face: Qwen3-4B وQwen3.5-2B وChronos-2. Metadata فقط، **دون أوزان**.
- [model_catalog.json](model_catalog.json) — مراحل تدريب النماذج الأساسية وسجل التقييم المطلوب؛ جميع checkpoints غير موجودة حتى الآن.

لا نرفع أوزان النماذج، أو بيانات الوسيط، أو نواتج التدريب إلى Git العادي. تحفظ محليًا في مسارات مستثناة من Git، مع manifest مستقل يشمل SHA256 والترخيص وسلسلة المصدر والنتائج ونسخة احتياطية قابلة للاسترجاع دون شبكة.

## تنزيل متعمد وغير تلقائي

```bash
python scripts/model_assets.py list
python scripts/model_assets.py download --model chronos-2 --confirm
python scripts/model_assets.py verify --model chronos-2
```

تتطلب عملية التنزيل وجود `huggingface_hub` في البيئة، ومساحة مناسبة، ومراجعة ترخيص الأوزان. لا تُنفَّذ هذه الأوامر عند استنساخ المستودع أو تشغيل CI. نبدأ تجارب XAUUSD مع LightGBM وCatBoost من بيانات حقيقية مدققة، ونقيّم Chronos وNHITS ونظراءها، ولا نخصص Qwen إلا بعد إنتاج عينات مؤرخة ومراجعة. أوزان النموذج الأساسي لا تصبح ملكية جديدة لنا بمجرد إضافة LoRA.

انظر [استراتيجية التدريب](../docs/03-TRAINING-STRATEGY.md)، و[مركز مصادر المشروع](../docs/16-SOURCE-HUB.md)، و[بوابات الجاهزية](../docs/09-PRODUCTION-GATES.md). **لا تداول حي ولا صلاحية لإرسال أوامر وسيط.**

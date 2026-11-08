# مركز نماذج Gold Intelligence AI — سجل موحد للمصادر والأصول

**النطاق:** XAUUSD فقط؛ بحث وتجارب ورقية؛ لا نماذج مؤهلة لتداول حقيقي.

**الهدف:** نقطة دخول واحدة تعرض جميع النماذج التي قررنا تقييمها، وتوضح الفرق بين **تسجيل المصدر** و**تنزيل الأوزان** و**التدريب**. هذا المستند ليس إثباتًا لوجود checkpoint، ولا بديلًا عن المخازن الفعلية للأوزان.

## 1) النماذج الجاهزة من جهات خارجية — مصادر مثبتة

| المعرف الداخلي | المصدر الأصلي | دور البحث | المراجعة المجمدة | وضع الأوزان |
| --- | --- | --- | --- | --- |
| `qwen3-4b` | [Qwen/Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B) | وكيل تحليل محلي / LoRA اختياري | `1cfa9a7208912126459214e8b04321603b3df60c` | **غير منزّلة** |
| `qwen35-2b` | [Qwen/Qwen3.5-2B](https://huggingface.co/Qwen/Qwen3.5-2B) | بديل أقل استهلاكًا للذاكرة | `15852e8c16360a2fea060d615a32b45270f8a8fc` | **غير منزّلة** |
| `chronos-2` | [amazon/chronos-2](https://huggingface.co/amazon/chronos-2) | توقعات احتمالية للسلاسل الزمنية | `29ec3766d36d6f73f0696f85560a422f50e8498c` | **غير منزّلة** |

**المرجع الآلي المعتمد للمراجعات والملفات المتوقعة:** [foundation_weights.lock.json](foundation_weights.lock.json). يحتوي على commit SHA لكل مصدر، لكنه **لا يحتوي أوزانًا** ولا بصمات SHA256 لملفات الأوزان نفسها؛ تتولد البصمات بعد تنزيل كل ملف محليًا وفحصه. مصدر قائمة المرشحين: [foundation_candidates.json](foundation_candidates.json).

## 2) النماذج التي نعتزم تدريبها أو مقارنتها

| المعرف | التقنية | المرحلة الحالية |
| --- | --- | --- |
| `lightgbm-xauusd` | LightGBM — baseline/تصنيف ورفض التداول | مخطط؛ لا checkpoint |
| `catboost-xauusd` | CatBoost — baseline مستقل | مخطط؛ لا checkpoint |
| `nhits-xauusd` | NeuralForecast / NHITS | مخطط؛ لا checkpoint |
| `nbeatsx-xauusd` | NeuralForecast / NBEATSx | مخطط؛ لا checkpoint |

التعلم المعزز (مثل PPO أو SAC) بحث مؤجل، وليس وزنًا مثبتًا أو نموذجًا جاهزًا معتمدًا. انظر [استراتيجية التدريب](../docs/03-TRAINING-STRATEGY.md). يضم [model_catalog.json](model_catalog.json) خط سير التدريب الأساسي، بينما يضم [foundation_candidates.json](foundation_candidates.json) المرشحين الأوسع، ومنها NBEATSx. لا تستخدم ظهور الاسم في أي سجل بوصفه دليل تنزيل أو تدريب.

## 3) مصادر الشيفرات المساعدة (وليست أوزان نماذج)

- نسخ شيفرات **Aurum** و**TradingAgents** و**Midas Agent** مجمدة في [vendor/snapshots](../vendor/snapshots) مع أدلة المصدر والترخيص والبصمات.
- سجل المصادر الأوسع: [sources.lock.json](../sources/sources.lock.json).
- توثيق الأرشفة ومراجعات الأمان والحقوق: [مركز المصادر](../docs/16-SOURCE-HUB.md).

وجود الشيفرة لا يعني صلاحية التشغيل أو امتلاك أوزان نموذج مدرب.

## 4) أين نخزن كل نوع من الأصول؟

| الأصل | المرجع الموحد على GitHub | الموقع الفعلي |
| --- | --- | --- |
| شيفرة المشروع والنسخ المسموح بها | Git repository | `src/`, `vendor/` |
| أسماء النماذج وإصداراتها والتراخيص المتحققة | هذه الصفحة + ملفات JSON | Git repository |
| أوزان النماذج الجاهزة | فهرس + مراجعة SHA + manifest | مخزن أوزان محلي **خارج Git**: `models/weights/` |
| Checkpoints/LoRA المدربة | manifest يشمل البيانات وcommit والتقييم | `models/checkpoints/` محليًا ونسخة احتياطية مستقلة |
| بيانات أسعار الذهب والوسيط | سجل حقوق ومخططات، لا عينات سرية | `data/` محليًا، مستثناة من Git |

**سبب عدم رفع جميع الأوزان مباشرة إلى Git:** GitHub يرفض الملفات العادية الأكبر من 100 MiB؛ وتسمح خدمة Git LFS بملفات أكبر حسب خطة الحساب، لكن لها حد حجم **لكل ملف** وحصص تخزين ونقل قد تستلزم رسومًا. أحجام الأوزان التقديرية للمرشحين الجاهزين في سجلنا: Qwen3-4B ≈ 8.06 GB، Qwen3.5-2B ≈ 4.57 GB، Chronos-2 ≈ 0.478 GB (المجموع ≈ 13.1 GB قبل ملفات إضافية). هذه **تقديرات من السجل لا نتيجة تنزيل فعلي**. لا نضيف LFS مدفوعًا أو نحجز مساحة أو نجزّئ ملفات safetensors تلقائيًا دون خطة متوافقة ومراجعة تكاليف وحقوق.

لمن يريد «كل المصادر من مكان واحد»: هذه الصفحة هي لوحة الدخول المركزية؛ أما الاكتفاء بروابط خارجية **فليس نسخة احتياطية مستقلة**. الاعتماد على مصادر منبع مثبتة لا يغني عن **تنزيل الأوزان ونسخها احتياطيًا واختبار استعادتها Offline**.

## 5) خطوات التنزيل المحلي **اليدوي** عند جاهزية العتاد والحقوق

```bash
# من جذر المستودع، داخل بيئة Python مناسبة
python scripts/model_assets.py list

# يتطلب huggingface_hub مثبتًا والتحقق من المساحة وحقوق الاستخدام
python scripts/model_assets.py download --model chronos-2 --confirm
python scripts/model_assets.py verify --model chronos-2

# اختياري لاحقًا وبعد فحص VRAM/RAM/SSD:
# python scripts/model_assets.py download --model qwen35-2b --confirm
# python scripts/model_assets.py download --model qwen3-4b --confirm
```

هذه الأوامر **غير منفذة هنا**، ولا تُشغل تلقائيًا في CI أو على جهاز المستخدم. لا نقبل أوزانًا نهائية قبل وجود manifest ببصمة SHA256 لكل ملف، وتحقق الترخيص والتشغيل المحلي دون شبكة ونسخة احتياطية قابلة للاسترجاع، ولا نرفع أي أسرار/بيانات وسيط/أوزان ضخمة إلى Git عادي.

## 6) قرار ما يزال معلقًا

**مكان النسخة الثانية المستقلة للأوزان:** تخزين محلي منفصل أو مخزن كائنات خاص، أو Git LFS بعد التحقق من خطة GitHub الفعلية وحدود حجم كل shard وحصصها وتكاليفها. لا نفترض موافقة على فواتير أو صلاحيات تخزين غير معلنة.

## روابط GitHub الرسمية لحدود التخزين

- [حدود الملفات العادية](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github).
- [Git LFS وحدود حجم الملف حسب الخطة](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage).
- [حساب استخدام وتكلفة Git LFS](https://docs.github.com/en/billing/concepts/product-billing/git-lfs).

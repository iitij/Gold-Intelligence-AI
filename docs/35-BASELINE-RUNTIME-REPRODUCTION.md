# إعادة إنتاج بيئة CPU الأساسية — 2026-11-18

أُنشئت بيئة Python نظيفة على جهاز Linux الحالي، وثُبتت فيها 29 حزمة من
`requirements-ci.lock` و`requirements-ml-baseline.lock` مع التحقق من SHA256
واشتراط الحزم الثنائية. لم تُعدّل إصدارات القفل أو بيئة التدريب الأصلية.

نجحت الاختبارات الـ215 داخل البيئة الجديدة، وأكد فحص الاعتماديات توافق
الحزم كلها. أعادت نماذج LightGBM وCatBoost المحفوظة إنتاج التنبؤات الستة
لآفاق 1 و4 و16 شمعة، بما فيها المعايرة، دون فرق عددي. قارنت أداة التحقق
مجموعة الحزم المثبتة كاملة مع اتحاد القفلين، وبصمات البيانات والنماذج
وموعد القرار مع المرجع السابق.

أُعيد تدريب نموذجَي الخروج المبكر من البيانات نفسها داخل البيئة الجديدة.
تطابقت معلمات التدريب وحدود العينات وسجلات الخروج والعائد تمامًا.
تطابق ملف LightGBM ثنائيًا أيضًا. اختلف ملف CatBoost الثنائي؛ وتطابقت
بنية الأشجار والخصائص وscale/bias بعد استبعاد معلومات النموذج الإدارية
من تمثيل JSON. لذلك لا يُدّعى تطابق الملفين الثنائيين لـCatBoost.

الأدلة المحلية:

- `artifacts/baseline-runtime-reproduction-20261118.json`: إصدارات الحزم وبصمات القفل والمرجع وفروق التنبؤات.
- `artifacts/baseline-rebuild-checks-20261118.json`: التثبيت والاختبارات والمقارنة مع إعادة التدريب النظيفة.
- `artifacts/quote-exit-policy-clean-runtime-20261118/report.json`: تقرير التدريب المعاد وسجلات الخروج.

أوامر إعادة التحقق، باستخدام مسارات إخراج جديدة:

```bash
uv venv --python .venv/bin/python .local/repro-baseline-20261118
uv pip install --python .local/repro-baseline-20261118/bin/python \
  --require-hashes --only-binary :all: \
  -r requirements-ci.lock -r requirements-ml-baseline.lock
PYTHONPATH=src:. .local/repro-baseline-20261118/bin/python -m pytest -q
uv pip check --python .local/repro-baseline-20261118/bin/python
PYTHONPATH=src:. .local/repro-baseline-20261118/bin/python \
  scripts/reproduce_baseline_runtime.py \
  --locks requirements-ci.lock requirements-ml-baseline.lock \
  --root artifacts/historical-strategies-2026-11-17-regime \
  --feed headway_xauusd_m15_20261110.csv \
  --reference artifacts/headway-latest-frozen-predictions-20261118.json \
  --output artifacts/baseline-runtime-reproduction-20261118.json \
  data/validated/headway_m15_native_extended_20261118.csv
```

الأدلة تخص بيئة CPU الأساسية على الجهاز الحالي، باستخدام Python 3.11.16
وuv 0.12.19. لا تشمل تثبيت نظام مستقل أو تجميد مكتبات النظام أو بيئات
NHITS وChronos وGPU وLLM وMT5. اختبار CI البعيد لهذه التغييرات لم يُنفّذ
ضمن هذا التحقق المحلي. تظل P02-02 قيد الإنجاز حتى تستكمل أدلة نطاقها،
ولا تغيّر هذه النتائج حالة بوابات البيانات أو اعتماد النماذج.

## فحص حزمة التغييرات للمراجعة

بعد إضافة اللقطات السوقية وفحوص البيانات، أُنشئت بيئة نظيفة مستقلة أخرى
من قفل CI وحده: ست حزم مع hashes، دون حزم ML. نجح فيها 234 اختبارًا
مع تخطي أربع وحدات اختبار تحتاج اعتمادات ML اختيارية. نجحت فحوص ruff
والقفل والمصادر المثبتة وSBOM المصنف والسياسات كما تنفذها Workflow CI.
وفي بيئة CPU الأساسية ذات 29 حزمة نجحت الاختبارات الـ244، ونجح اختبار
التدريب الاصطناعي لـLightGBM وCatBoost. هذه نتائج محلية للتغييرات الحالية؛
لا تثبت بحد ذاتها تنفيذ CI بعيد على GitHub.

## تحقق 25 نوفمبر 2026 على الجهاز الحالي

أُنشئت بيئتان جديدتان دون اتصال باستخدام ذاكرة حزم uv المحلية
و`--require-hashes --only-binary :all:` على CPython 3.11.16.
نجحت فحوص سير عمل CI محليًا في بيئة القفل الأساسي وحده (267 اختبارًا
ناجحًا و7 تخطيات للاعتماديات الاختيارية). نجحت اختبارات بيئة CPU ذات
29 حزمة كلها (294 اختبارًا)، واجتازت LightGBM وCatBoost تجربة التدريب
الاصطناعية. بقي القفلان دون تغيير، وأبلغ preflight أن بوابات الاعتماد
لا تزال مغلقة.

سجل GitHub لنسخة `1bbcfb9` حالتي فشل حديثتين:
[CI](https://github.com/iitij/Gold-Intelligence-AI/actions/runs/45637783830)
و[ML smoke](https://github.com/iitij/Gold-Intelligence-AI/actions/runs/45637783771).
أعاد استعلام GitHub صفر خطوات لكل مهمة، ولم يتوفر سجل التنزيل
(`BlobNotFound`). لا يثبت هذا سبب الفشل أو أن الاختبارات بدأت، ولا
يحل نجاح الاختبار المحلي محل نجاح CI البعيد لهذه النسخة.

أُعيد بناء عميل Python لـMT5 من نسخة Windows المضمّنة 3.11.9 وعجلتي
MetaTrader5 5.0.6231 وNumPy 1.26.4. الأمر يطابق بصمات الأرشيفات الثلاثة
قبل إنشاء المجلد، ولا يستخدم مدير حزم أو شبكة. رفضت تجربة مستقلة
أرشيفًا مختلف البصمة قبل إنشاء الإخراج.

```bash
python scripts/stage_headway_windows_python.py \
  .local/mt5-inspect .local/repro-headway-winpy-20261125
```

نجح تحميل الحزم وحساب NumPy تحت Wine 11.21 Staging. استُخدم العميل
المعاد لاسترجاع دفعة XAUUSD مغلقة من Headway-Demo بالقراءة فقط، من
16:46 إلى 16:48 على ساعة المنصة. حفظت الدفعة 1,829 تحديثًا، وبصمة
`acquisition/20261125/native-20261125-rebuilt-client-1648/closed-request.json`
هي `42cc973a580df91ea970b4ec5e334221e4d822a0c997fe73973d8a9d382fd197`.
بصمة `stage.json` هي
`aa015c5ba8b4b7c04b8a8f8d76179aea0db72afcb8cab00fadee139c07d7bb5b`.
تثبت التجربة إعادة بناء عميل Windows على Linux واستخدام منصة موجودة.
تثبيت MT5 أو Wine مستقل والتحقق على جهاز Windows أصلي يظلان غير مثبتين.

أظهر فحص النسخة التالية `70ed4cf` الحالة نفسها في GitHub:
[CI](https://github.com/iitij/Gold-Intelligence-AI/actions/runs/45638443846)
و[ML smoke](https://github.com/iitij/Gold-Intelligence-AI/actions/runs/45638444188)
انتهيا بالفشل دون خطوات معروضة. يبقى سبب الفشل غير مؤكد.

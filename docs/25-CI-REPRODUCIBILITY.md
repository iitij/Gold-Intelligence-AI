# تجهيز بيئة CI: قفل الاعتماديات وسلسلة التوريد

**الهدف:** الانتقال من حدود إصدارات حزم Python المتغيرة إلى ملفات exact versions + SHA256 قابلة للمراجعة. يُحفظ المفتاح مرة واحدة، ثم لا يحدث `pip install -U` ولا `uv lock --upgrade` تلقائيًا.

## ما حدث أولًا

- ثُبتت GitHub Actions الأساسية بالـ Git SHA عند نسختي checkout v5 وsetup-python v6؛ نقل CI إلى Node24-compatible.
- أُنشئت Workflow لمرة واحدة فقط `.github/workflows/generate-ci-lock-once.yml` تُستدعى عند أول إضافة لها إلى main. تستخدم Python 3.11 و`uv==0.10.0` لحل اعتمادات **dev/test فقط**، وتنتج `requirements-ci.lock` مع hashes ثم تُزيل نفسها داخل فرع مراجعة مستقل؛ لا تدمج تلقائيًا.
- بعد مراجعة Workflow الناتجة واعتمادها في PR، يبدّل CI تثبيت `pip install -e '.[dev]'` الديناميكي إلى `python -m pip install --require-hashes -r requirements-ci.lock` ويستخدم `PYTHONPATH=src` بدلاً من بناء editable متغير.
- لا يُعد هذا تثبيتًا نهائيًا لكل اعتمادات ML/agents؛ تحتاج هذه حزمًا مستقلة وقفلًا ملائمًا للـGPU ونظام Ubuntu بعد فحص العتاد. ولا يعتبر هذا ضبط OS/Python patch أو إثبات بناء Offline.

## يجب قبل اعتماد lock

1. التأكد من فحص كل سطر وإصدار/hash والاعتماديات العابرة.
2. تشغيل CI على فرع الاختبار من ملف القفل دون تحميل نموذج أو بيانات وسيط.
3. إعداد SBOM قابل للمراجعة وفحص CVE مؤرخ، دون تعطيل فحص الانكشاف الأمني لمجرد تجميد نسخ المنبع. كل إصلاح مستقبلي يجب أن يكون تعديلًا داخليًا من PR مع تفسير.
4. عدم استخدام Workflow التوليد بعد أول تشغيل، لأنها توفّر مسار تحديث غير مراقب.

**التداول الحقيقي ممنوع؛ هذه خطوات سلسلة توريد برمجية فقط.**

## تم التنفيذ — قفل بيئة CI

تم توليد `requirements-ci.lock` مرة واحدة على GitHub Actions بنسخ محددة وبصمات SHA256 لكل wheel معتمدة لـPython 3.11 (pytest/ruff وملحقاتهما). بعد نقل القفل إلى `main` فإن `.github/workflows/ci.yml` يستخدم `pip install --require-hashes -r requirements-ci.lock` و`PYTHONPATH=src`، ولا يعيد حل النسخ من `pyproject.toml` في كل تشغيل. يحرس `scripts/verify_ci_lock.py` سياسة التثبيت، وتثبت GitHub Actions بالـCommit SHA.

هذه خطوة **جزئية** من P02-02 وP01-05 فقط. لا نعد بوجود wheelhouse Offline، ولا قفل كامل لكل Extras، ولا SBOM أو CVE review مكتمل، ولا إعادة إنتاج OS/driver/GPU/MT5 حتى تكتمل أدلتها. يظل اعتماد أي تغيير على ملف القفل مراجعة بشرية منفصلة.

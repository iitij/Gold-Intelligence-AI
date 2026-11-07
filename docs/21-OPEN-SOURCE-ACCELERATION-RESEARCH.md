# البحث الإضافي لتسريع Gold Intelligence AI — 2026-11-08

**الحالة:** قرار استكشافي مبني على فحص GitHub والوثائق، وليس دمجًا تشغيليًا أو إثباتًا لنتائج تداول.  
**المستودع الأساسي:** [Gold-Intelligence-AI](https://github.com/iitij/Gold-Intelligence-AI)  
**سجل النسخ الثابتة:** [research_candidates_2026_11_08.lock.json](../sources/research_candidates_2026_11_08.lock.json)  
**المعيار:** XAUUSD فقط، محلي، تجريبي، بلا صلاحية تداول حقيقي، ومن دون سحب تحديثات المنبع.

## القرار التنفيذي

أسرع مسار هو إنهاء **بيانات الوسيط → خصائص لا ترى المستقبل → Baselines → محاكاة قابلة للتنفيذ → نموذج مدرب ومُعاير**. لا نحتاج استنساخ محرك backtest ثانٍ أو دمج 10 مستودعات أخرى. تأتي أهمية المشاريع الجديدة من مساعدتها على سد 3 فجوات فورية: جودة البيانات، سرعة تجارب ML، وربط MT5 دون خرق الأمان.

| المصدر | النسخة | الترخيص | القرار | السبب |
|---|---|---|---|---|
| [Pandera](https://github.com/unionai-oss/pandera) | `da881ea` | MIT | **اعتمادية مرشحة P0** | اختبارات الأعمدة والأنواع والجودة؛ لا تنوب عن التوقيت الفعلي |
| [MLForecast](https://github.com/Nixtla/mlforecast) | `16cabe1` | Apache-2.0 | **اعتمادية مرشحة P0** | تسريع rolling/lag features وCV؛ يجب منع future exogenous |
| [StatsForecast](https://github.com/Nixtla/statsforecast) | `9e1f760` | Apache-2.0 | اعتمادية مرشحة P1 | نماذج ساذجة وإحصائية للمقارنة؛ ليست إثبات ربح |
| [mt5linux](https://github.com/lucas-campagna/mt5linux) | `7460cbc` | MIT | PoC معزول للقراءة P0 | خيار اختبار Windows Python تحت Wine؛ لا اعتماد على binary غير موثق |
| [Metatrader-Bridge](https://github.com/BorjaGomezSolorzano/Metatrader-Bridge) | `d4887a8` | BSD-3-Clause | **أرشفة شيفرة بحثية فقط** | مثال صغير لرسائل ملفات MQL5/Python؛ يحوي وظائف أوامر ولا تظهر اختبارات |
| [oos-lab](https://github.com/OutOfSampleLab/oos-lab) | `d09ba12` | MIT | **أرشفة بحثية فقط** | تحقق مستقل من PBO/DSR؛ مشروع جديد ولا يكفي الاعتماد على إعلانه |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | `fa4c7a8` | LGPL-3.0 | **مرجع هندسي، دون نسخ** | إدارة أحداث وأوامر/مخاطر؛ محرك Rust كبير وغير جاهز لربط MT5 لدينا |
| [andhikapraa/mt5-bridge](https://github.com/andhikapraa/mt5-bridge) | `a1bdfbf` | MIT | مرجع فقط | HTTP trade endpoints و `seccomp:unconfined` يحتاجان مراجعة أمنية |
| [ishan-parihar/metatrader-bridge](https://github.com/ishan-parihar/metatrader-bridge) | `189eb5f` | MIT | مرجع فقط | واجهات أوامر ومساعدين يجب عدم تعريضها مباشرة للوكيل اللغوي |
| [Goldbacktest](https://github.com/AMItheWise/Goldbacktest) | `4c1b3d8` | MIT | مرجع فقط | مثال Tick/Bid/Ask وDST، بلا أدلة كافية لاعتماد الاستراتيجية |

> **مهم:** هويتنا ليست عدد المشاريع المستوردة. `snapshot` لا يعني `approved` أو `safe`. نسخة Git ثابتة لا تجعل اعتمادياتها مثبتة؛ نحتاج wheelhouse/lock/hashes ونقطة مرجعية لا تتبدل. التراخيص الإضافية وحقوق البيانات والأوزان منفصلة.

## نتائج فحص سريع لمصادر عالية الفائدة

- `MLForecast`: ترخيص Apache-2.0 و43 ملفًا في مسارات الاختبار وقت الفحص. قد يخدم خصائص LightGBM/ CatBoost، لكن غياب ضبط `available_at` للمتغيرات الخارجية قد يسرب المستقبل.
- `Pandera`: MIT و234 ملفًا في مسارات الاختبار، مناسب لجودة البيانات المنظمة؛ لا يحل محل تدقيق تاريخ UTC/DST ولا تسوية أسعار وسيط التداول.
- `mt5linux`: MIT و12 ملفًا في مسارات الاختبار. يستخدم Wine وRPyC، وبعض أشكال التشغيل تعتمد على خادم منفصل. لا نعرض endpoint على الشبكة ولا نمرر أي صلاحية تنفيذ.
- `BorjaGomezSolorzano/Metatrader-Bridge`: 8 ملفات فقط ولم نعثر على مسار اختبارات آلي؛ أسلوب الملف-للملف قد يتطلب معالجة السباق، انتهاء المهلة، التكرار واستعادة الحالة.
- `oos-lab`: 33 ملفًا و8 ملفات اختبار؛ استخدمه كـ **أداة مقارنة إحصائية محتملة** مقابل Aurum وحساباتنا المرجعية، لا كمصدر للحقيقة.
- `NautilusTrader`: LGPL-3.0 ومحرك Rust كبير؛ له مبادئ مهمة (event sourcing وreconciliation)، لكن دمجه الآن سيؤخر أول نموذج مدرب ويكرر Aurum.

عدد ملفات الاختبار مؤشر على حجم التغطية، **ليس** درجة ثقة أو نتيجة تحقق مستقل. لم أجرِ اختبارات تشغيل شاملة لكل مستودع جديد.

## ما الذي يمكن نسخه دون أن نصنع فوضى؟

يُسمح **بأرشفة مراجعتين بحثيتين فقط** من مصدرين صغيرين مرخصين — oos-lab وMetatrader-Bridge — في مسار معزول `vendor/research_refs/` مع manifests SHA256 والتراخيص. هذا **ليس إدماجًا** في مسار التنفيذ، ولا تثبيت Python ولا منح MT5 access. لا تُستخدم شفرة الأرشيف إلا بعد مراجعة اختبارية مستقلة.

أما MLForecast وPandera وStatsForecast فالأفضل تثبيت اعتماداتها بعد اختيار إصدارات حزم قابلة لإعادة الإنتاج، وليس نسخ عشرات/مئات الملفات إلى نواتنا. إذا قررنا تعديل جزء منها فسنأخذ *وحدة محددة* بصمة وترخيصًا واختبارات، وليس full fork غير مطلوب.

NautilusTrader وAGPL والمتغيرات المبنية على وكلاء لديهم صلاحية أوامر تبقى خارج نواة المشروع.

## خطوات الوصول لأول نموذج مدرب بأسرع مسار مسؤول

1. **الآن:** احمِ `main` وابدأ SBOM/مراجعة اعتماديات ثابتة. مرجع [#2](https://github.com/iitij/Gold-Intelligence-AI/issues/2)، [#9](https://github.com/iitij/Gold-Intelligence-AI/issues/9)، [#11](https://github.com/iitij/Gold-Intelligence-AI/issues/11).
2. **البيانات أولًا:** فعّل سكريبت MT5 M15 للقراءة فقط، ثم حسّن تصدير Tick/Bid/Ask ومواصفات الرمز وسجل توقيت الوسيط. مرجع [#13](https://github.com/iitij/Gold-Intelligence-AI/issues/13)–[#18](https://github.com/iitij/Gold-Intelligence-AI/issues/18).
3. **الاختبار السريع قبل AI:** استخدم Pandera المرشح لفحص عقود البيانات، وStatsForecast أو قواعد بسيطة لإثبات أن pipeline يعمل، ثم MLForecast وLightGBM/ CatBoost على نفس تقسيمات التحقق ومعايير تسرب الزمن. مرجع [#19](https://github.com/iitij/Gold-Intelligence-AI/issues/19)–[#25](https://github.com/iitij/Gold-Intelligence-AI/issues/25).
4. **أثبت الأثر الاقتصادي:** حوّل توصيف BUY/SELL/NO_TRADE إلى نتيجة بعد تكلفة السبريد والعمولات والانزلاق عبر Tick/Bid/Ask، مع Walk-Forward وHoldout مستقل. مرجع [#35](https://github.com/iitij/Gold-Intelligence-AI/issues/35)–[#38](https://github.com/iitij/Gold-Intelligence-AI/issues/38).
5. **توقف عند المعيار:** إذا لم تتفوق الخوارزمية الجديدة على baseline بعد جميع التكاليف، فلا تدرّب Qwen لتحويل نتائج ضعيفة إلى حوار جيد. ابدأ Qwen وChronos فقط إذا أضافا قيمة قابلة للقياس أو كان لهما دور منفصل في التفسير.

### تجربة ثلاثية سريعة وعادلة
- **A:** No-change / fixed historical-momentum baselines.
- **B:** LightGBM أو CatBoost مع خصائص سببية، دون LLM.
- **C:** B + شروط جودة البيانات / regime / no-trade.
- **D (مشروط):** B/C + Chronos أو Qwen. كل فرع يخضع لنفس فترات الاختبار والسبريد والتكاليف مع تسجيل كل محاولة.

لا نختار النموذج باستخدام Holdout المقفل، ولا نفترض أن forecast أفضل يعني تداولًا أربح.

## المخاطر الجديدة التي يجب ألا نفوتها

- **استدعاء وظائف التداول عبر LLM**: منعه على مستوى API permissions. لا تُعرّض جسر MT5 كامل الصلاحيات لوكيل Qwen.
- **الجسور والملفات الثنائية**: أي خادم/خدمة تحت Wine يعزل على loopback بعملية غير مميزة ويراجع مصدر كل binary وعلاقته بالتراخيص/الحساب، قبل اختبارات Demo.
- **MQL5 Strategy Tester**: `WebRequest()` غير مدعوم بداخله؛ لا نبني Backtest يعتمد على اتصالات HTTP حية. نستخدم محاكاة Python الحدثية، ثم اختبار مطابقة أمام MT5 Demo.
- **المعايرة تحت تغيّر الأنظمة**: التدريب على عام واحد جيد لا يكفي؛ نحتاج جلسات سوق وأحداث عالية التقلب واختبارات انتقال النظام.
- **الحصول على Alpha**: نموذج دقيق في التنبؤ قد يخسر ماليًا بعد السبريد والتمويل؛ الهدف قيمة اقتصادية موجبة بعد التكاليف، وليس Accuracy وحدها.

## سياسة عدم العودة إلى المنبع

سجل المصدر هنا يحفظ Commit SHA كاملة، وأرشيف البحث يحفظ الأصول محليًا بعد مراجعته. **لا نحدّث نسخة أصلية تلقائيًا مستقبلًا**. عندما نبدأ إدخال أي مكتبة إلى بيئة الإنتاج، سنُثبت Wheel/SDist، Hashes والاعتماديات العابرة في مخزن خاص، لتعمل بدون العودة إلى المنبع. لا يُعاد فتح مراجعة المصدر إلا بقرار تغيير داخلي موثق.

## قرار نهائي

**نعم للتوسعة المدروسة؛ لا لدمج عشرة روبوتات.** P0 عمليًا: Pandera + MLForecast (بعد بيانات الوسطاء) وتجربة read-only للاتصال MT5. ملفات oos-lab وMetatrader-Bridge يمكن أرشفتها للمراجعة فقط. بقية المشاريع تُفيدنا مرجعيًا بلا زيادة عبء الصيانة.


## حالة الأرشفة المنجزة

أُنجز الاستيراد لمرة واحدة إلى `vendor/research_refs/` على فرع المراجعة، وحُذفت Workflow؛ راجع [مراجعة الأرشيف البحثي](22-RESEARCH-ARCHIVE-REVIEW.md). **الأرشيف ليس معتمدًا للتنفيذ.**

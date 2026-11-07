# إنشاء Milestones حقيقية لـ52 GitHub Issue — سياسة مرة واحدة

أُضيفت جميع Labels المطلوبة مباشرة على GitHub وتم التحقق من مطابقتها مع `planning/backlog.json`، دون تعديل نصوص المهام أو إغلاقها. لا توجد تواريخ إنجاز مخترعة.

إكمال إعداد Milestones يتم مرة واحدة فقط بواسطة `.github/workflows/create-phase-milestones-once.yml`، ويعمل على `main` ضمن المستودع الخاص فقط. يمنح Workflow `issues:write` لإنشاء **12 milestone** من أسماء المراحل الحالية، ثم يربط **52 Issue موجودة** بمراحلها بعد التحقق من العلامة `GOLD-TASK-ID`. لا ينشئ Issues جديدة ولا يحذف أو يغلق أي مهمة، ويرفض التعارض مع milestone محدد مسبقًا.

`scripts/sync_milestones_once.py --dry-run` يعمل محليًا دون GH أو توكن ويطبع عدد المراحل والمهام. خيار `--confirm` يرفض العمل خارج `GITHUB_REPOSITORY=iitij/Gold-Intelligence-AI` و`GITHUB_REF=refs/heads/main` وبلا `GH_TOKEN`.

بعد التشغيل الناجح يرفع Workflow فرعًا مستقلاً يحذف ملف Workflow ذات الصلاحيات العالية، وتجب مراجعة ودمج الفرع فورًا. **لا نترك Workflow مدعومة بكتابة Issues تعمل دوريًا**.

هذه الإعدادات لا تحل مشكلة `main.protected=false` الحالية، ولا تبرر تحويل المستودع إلى Public؛ حماية PR تحتاج ميزة GitHub مدعومة على الخطة المختارة.

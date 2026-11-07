# سجل فجوات تدقيق 2026-11-07 — مستقل وقابل للمراجعة

**المصدر:** [التدقيق التقني](../docs/17-INDEPENDENT-TECHNICAL-AUDIT.md).

هذا سجل تحسين شروط القبول للمهام الحالية، ولا يدعي أن الـIssues أُغلقت. لا ننشئ مهام مكررة قبل مراجعة مخرجات وتبعيات المهام الأصلية؛ **المرجع النهائي للمهام الحالية يبقى \`planning/backlog.json\`**.

| ID | مستوى | الفجوة / التحسين | Issue موجودة | دليل القبول المقترح | حالة |
|---|---|---|---|---|---|
| AUD-01 | P0 | Protected main، CIRequired، مراجعة، منع force push | #2 | GitHub branch ruleset + test attempted bypass | pending |
| AUD-02 | P0 | Lock Python/Actions/container مع hash + SBOM/CVE scan | #9 #11 | reproducible clean build + inventory + triage | pending |
| AUD-03 | P0 | Vendor interoperability وعزل مساحة الاسم والاعتماديات | #6 #7 #8 #30 | single gold event contract + isolated integration tests | pending |
| AUD-04 | P0 | MQL5 Compile وMT5/Wine smoke + hardware evidence | #10 #14 #39 | compiler log + local demo connectivity | pending |
| AUD-05 | P0 | Timezone/DST/market calendar وvalid Bid/Ask Tick coverage | #13 #14 #16 | tests cross DST rollover + broker/ref comparison | pending |
| AUD-06 | P0 | Leakage-free macro \`available_at\`, COT Friday release | #17 | reproducible point-in-time join tests | pending |
| AUD-07 | P0 | Event-driven execution matched to broker with latency/fills | #35 #40 | partial/rejected/gap/spread stress fixtures | pending |
| AUD-08 | P0 | Lot-grid/max bound bug، risk limits، order/margin reservations | #40 | property tests incl max not aligned with step; concurrency + broker P&L tests | pending |
| AUD-09 | P0 | Train tiny baseline + independent holdout before ensembles | #22 #23 #24 #36 #38 | signed OOS evidence and experiment ledger | pending |
| AUD-10 | P1 | Drift/uncertainty detection + rolling re-calibration under governance | #25 #44 | rolling reliability and retraining proposal tests, no auto promotion | pending |
| AUD-11 | P1 | LLM prompt injection + agent evidence alignment + quant-only ablation | #31 #32 #34 | tool-denial tests, conditional P&L delta and latency | pending |
| AUD-12 | P1 | Cross-broker execution economics and spot/futures basis/roll | #13 #16 #19 | cost/effective spread tests, future-release no leakage | pending |
| AUD-13 | P1 | Independent internal bugfix process for frozen sources | #4 #9 #45 | patch log + CVE triage without upstream auto-sync | pending |
| AUD-14 | P1 | Model/artifact provenance and offline recovery | #26 #45 | verified local model bytes + tested restore and rollback | pending |
| AUD-15 | P1 | CI test depth, fault injection, disaster restart | #39 #43 #46 | adversarial integration tests + recovery exercise | pending |
| AUD-16 | P1 | Documentation drift and GitHub issue status parity | #3 #4 | DEC-006/009 and STATUS corrected, issue labels/milestones | pending |
| AUD-17 | P1 | Fair external baseline contest and economic significance | #22 #38 | matched costs, risk capital, time windows and multiple tests | pending |
| AUD-18 | P2 | Research-only RL gated by simulator calibration | #48 | evidence of simulator realism and incremental value | deferred |

## بحث جديد يُقترح كمهام مستقلة لاحقًا، وليس عملاً أنجز

1. **AUD-R01 — Alpha Research Tournament:** نظام تجارب يقارن قواعد الأساس، ونماذج متعددة، واستخدام بيانات الماكرو وأي LLM تحت ميزانية محاولات وسجل شامل.
2. **AUD-R02 — Gold Microstructure and Basis:** توثيق خصائص CFD/Spot/GC Futures وCOT ومصادر order-flow الممكنة، فقط بعد ترخيص البيانات وتوقيت النشر.
3. **AUD-R03 — Champion/Challenger/Shadow Model Evaluator:** خط موافقات وتراجع إلى نموذج سابق، ومراقبة تغير التوزيع والمخاطرة في التداول التجريبي.
4. **AUD-R04 — Independent Broker Cost Observatory:** إحصاء spread/slippage/fill quality بحسب الجلسة والأحداث، مع مقارنات مستقلة بين وسيط فعلي وبيانات مرجعية.

هذه أفكار قابلة للاختبار يجب أن تتحول إلى Issues منفصلة فقط بعد مراجعة التبعيات وعدم تداخلها مع 48 مهمة مفتوحة. بدون بوابات G0-G3 لن نخصص موارد للبحث عالي التعقيد.

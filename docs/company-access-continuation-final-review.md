# Final targeted continuation review

Input: `company-access-targeted-30-continuation-v1-40317605371(1).zip`, supplied by the user. Snapshot SHA-256 (canonical serialization): `0cfcb1dfed7e1649b7c2ec71a03e989eafd36784b34ba368f907dde9b94ed6c0`.

Validated immutable parent, complete request ledger, cached payload hashes, fixed plan, source-rebuilt normalized candidates and every review row. Acquisition ended at PLAN_COMPLETE, 44/48 attempts. No new requests were made. PLAN_COMPLETE means the bounded query plan ended, not geographic inventory completeness. Do not rerun.

241 pending candidates are appended as a separate deployed batch, with original keys and provider assertions. All 183 approved office artifacts remain byte-identical. All 480 historical decisions and 553 earlier pending rows remain unchanged: 1,274 total review records, 794 pending. Default view focuses the new batch. Previously saved composite sessions remain compatible; suggestions do not initialize decisions.

Final triage: **24 credible, 206 exceptions, 11 suggested exclusions**. Three key exceptions are surfaced first. New scoped rules hold suspended/closed locations out of the credible group and identify parking, civil-defense infrastructure, parcel lockers and storage facilities even when duplicate flags exist. Flags remain available; no duplicate is merged or human reject recorded. Earlier-batch suggestions remain stable. Manufacturing businesses are not excluded merely by industry; corporate/R&D/mixed-site distinctions remain evidence-led.

Representative trace is displayed in the Console:

- SMIC main POI and SO8 building are already in prior pending inventory, not newly absent. Gate/building identity is not a verified office.
- Huahong group, Hongli facilities, building and parking POIs remain distinct; exact dispositions are derived from the checkpoint.
- USI Zhangdong 1558 is already pending. The focused Shengxia sales-office query returned the older facility, not a separate new sales-office POI.
- Both AMD name-search POIs were returned but are outside the exact 30-minute polygon. Zhangdong 1387 agrees with the official address; this does not override coordinate clipping. Rongke 118 is a distinct provider assertion.
- OMNIVISION group POI has a changed historical assertion and remains isolated; the historical decision is untouched. Campus, west tower, parking and civil-defense points do not establish additional corporate offices.

Public source links and their limits accompany the representative findings and relevant new candidate exceptions. The 24 credible records are mapped-office suggestions, not a claim that all were individually verified against official sources. No verified-physical confidence upgrade occurs.

Reproduce offline with `node scripts/company-access/discovery/final-review.mjs ARTIFACT_DIR FRESH_OFFLINE_DIR`. Pass that directory as the sixth review-build argument; normal builds still exclude all real review data. The final artifact and new prepared records are outside git.

Next user action: open Company Review Console, enter reviewer name, use **可信候选 → 抽查本组（最多8条） → 批量确认本组** only if satisfied. Then **重点核实 → 只看关键例外** for three exceptions. Leave the remaining uncertainty pending. Export **导出决定与历史** for a later independently validated canonical import; no CSV and no manual artifact upload are needed.

Validation: 170 JavaScript tests pass; actual release reconciliation confirms 183 offices, 480 history, 553 prior pending + 241 new pending. Economic guards remain 1,212,066.713237 and 37.6335253%. Browser visual QA remains unverified due the managed-preview connection failure already observed. No merge or production deployment.

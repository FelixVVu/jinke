# Targeted 30-minute continuation — review only

The first targeted snapshot is frozen at 19 requests, 300 queued candidates and 9 additional in-scope candidates retained in its cap audit. The approved inventory is now **183 offices**, with **480 historical decisions** and **553 pending** (291 recovered + 262 original targeted). This change makes no acquisition or human decision itself.

## Execute

Use the existing **Company Access targeted 30m continuation (manual review only)** workflow at `.github/workflows/company-access-amap-pilot.yml`. Click **Run workflow**, select **review/company-access-scaffold**, then **Run workflow**. No inputs or new credentials. The single acquisition step reuses `JINKE_AMAP_KEY`; tests never receive it. Never use **Re-run jobs**.

The restore step establishes both original-targeted and continuation run histories. It must find the original snapshot with the pinned SHA-256 and the latest started child's checkpoint. Missing/expired artifacts, changed parent, unprovable history or interrupted acquisition without a checkpoint stop before any provider call. The original artifact currently expires on **2026-11-23**; restore intentionally fails closed after that rather than creating a fresh budget. Downloaded checkpoints embed the parent and should be retained for review/import.

A separate `targeted-30-continuation-v1` checkpoint contains the immutable parent plus the complete request/response prefix. The original workflow's concurrency group is retained. The plan and latest ledger are validated on every resume. Retries count against **48 attempts total across original and child**, leaving **29** before continuation. Per execution is reduced to **12**, pacing stays **1,500 ms**, one retry at **3,000 ms**, page size **25**, maximum **3 pages per stream**. Reservation is saved before network I/O. Exhausted/uncertain queries are skipped, adjacent pages cannot leap over them, and broader connectivity failures open the existing circuit breaker. Cached queries and short-page streams are never reacquired. Pilot 3 is never restored or restarted.

## Coverage and precision

The fixed order first considers existing cached first pages (no calls), then six source-backed name streams, then page 2 of the original geographic streams in interleaved region order, then original name page 2, then geographic page 3. Supplemental name pages are lower priority. The parent has **10 full geographic first pages** awaiting continuation, **6 short geographic pages** and **2 full original name pages**. All cells remain inventory-incomplete; a short page never means an empty area. There is no 40/50-minute expansion.

The old 300 *raw candidate* stop is replaced by a **300 active-review-slot bound for this targeted campaign**, not a higher API quota. Active slots count credible suggestions and important exceptions, carrying forward the 4 existing targeted priority exceptions. Before each request 25 slots of page-size headroom are required. Known historical/pending provider IDs consume no new slot. Uncertain or suggested-exclusion records do not consume active slots but **remain pending**, fully included in the review bundle, audit and provider cache. No filtering deletes source evidence or records a human reject. At most 48 × 25 source observations can exist under the lifetime request bound. Nine cached overflow candidates can be prepared without network; currently 8 are exceptions and 1 a suggested exclusion, none credible enough for automatic trusted grouping.

The unchanged coordinate normalization and exact 30-minute clipping precede triage. Shared precision rules keep parking, food, entrances, construction and unrelated facilities out of the credible worklist. Manufacturing company identity is not an exclusion: mixed corporate/R&D/manufacturing addresses remain important exceptions, and explicit manufacturing-only evidence is distinguished. Same-name/office conflicts remain unresolved; no fuzzy merging.

## Source-backed leads, checked 2026-10-26

- [AMD locations](https://www.amd.com/en/corporate/locations.html): 张东路1387号, 环科路669号 and 博云路2号. New `AMD` and `超威半导体` searches; three locations must not be merged.
- [OMNIVISION](https://www.ovt.com/company/contact-us): 上科路88号 Shanghai technology-company location; 松江荣华路211号 is a different facility. New `豪威科技` and `OMNIVISION` streams. Corporate-location match alone is not proof of office use.
- [USI sales office](https://www.usiglobal.com/en/contact-usi?id=5d9918d8-cd62-4453-99e0-e9e6680c1a9d): 盛夏路169号, motivating a focused `环旭电子 盛夏路` stream. [张东路1558号](https://www.usiglobal.com/en/global-locations?location_id=usi-shanghai-zhangjiang-china) describes design/manufacturing; it is not interchangeable with the sales office or an individual building POI.
- [Huahong group directory](https://www.huahong.com.cn/?id=46&m=channel): 碧波路177号A区四楼 group office versus 哈雷路288号 subsidiary campus. Existing name pagination is reused; parent/subsidiary identity stays separate.
- [SMIC SSE profile](https://www.sse.com.cn/star/market/stocklist/info/company/index.shtml?COMPANY_CODE=688981): 张江路18号 corporate contact. Existing name page 2 is reused; a campus gate, production facility or S08 building is not automatically a confirmed office.
- [Pudong Software Park directory](https://www.spsp.com.cn/企业孵化与投资融资): a bounded `达观数据` stream supplements geography. Historical incubation is a discovery lead, never a current-tenancy assertion.

These are offline reviewed source leads with dates and limitations. No runtime website scraping or extra geocoding calls. Name + exact street-number matches attach narrow corroboration to the exact returned row. Facilities and mixed campuses remain exceptions. Suggestions cannot change canonical names, identity, human status or mapped confidence. Representative reports separate raw name hits, in-scope pending matches, and confirmed offices; source-address leads with no coordinates remain unlocated.

## Review without CSV

Download `company-access-targeted-30-continuation-v1-<run id>`. On the same Review Console choose **追加待审候选**, open **review/review-bundle.json**. Its embedded, validated second-pass pack loads together with candidates. The existing queue, locked history, notes and decisions remain intact; only the new batch is focused. A prior session backup is downloaded before append. On a page reload, reopen the same bundle to restore its locally saved composite session; retain exported JSON for durable backup.

Use **可信候选 → 抽查本组（最多8条）**, then explicit **批量确认本组** only after checking the group. Use **重点核实 → 只看关键例外** for mixed campuses, identity conflicts and source-backed exceptions. All other uncertainty can remain pending. **导出决定与历史** produces one JSON for source-rebuilt canonical import; opening an artifact or reading a suggestion never accepts anything. Provider assertion changes on continuation are audit-held; incompatible reappend fails visibly rather than replacing decisions.

Artifacts include key-free snapshot, normalized candidates, per-cell query pages/status, exclusions, triage, source links and pending JSON/CSV. No real company data or key is committed; normal production builds still omit review data. PR #20 remains draft, the same Review Site/audience is retained, and the 183 approved office GeoJSON and economic model are unchanged.

# Company discovery coverage repair — 2026-10-23

The 145 approved office locations are a small identified inventory, not a complete
inventory of the 30-minute reach. This change recovers omitted observations from
the three immutable AMap caches, adds geographic and representative-company
diagnostics, and prepares a narrower next discovery plan. It makes **zero new API
requests** and approves **zero records**. All 145 approved features and 442 prior
decisions/notes remain unchanged. No 40/50-minute acquisition is enabled.

## Root causes and measured gaps

| Stage | Finding | Remedy |
| --- | --- | --- |
| Provider scope | Historical queries use only company subcategories, missing potential corporate/R&D POIs in broader categories. | Stage broader corporate/research discovery and source-backed name searches; discovery eligibility is separate from office acceptance. |
| Category parsing | The historical single-code regex rejects `170100\|170200`, `170200\|070000`, etc. even when one code is a company. | Parse complete pipe-separated six-digit codes in the new recovery path. Preserve historical preparation policy and snapshot/bundle hashes. Mixed-use records remain exceptions. |
| Clip/reuse | Pilot 2 discarded returned POIs outside its exact 10-minute polygon, including locations inside 20/30 minutes. | Reprocess original WGS84-normalized observations against exact 30-minute reach. Keep the original exclusion reason and every query/snapshot reference. |
| Query ordering | Pilot 3 allocated its lifetime budget to first pages across 83 cells. | A smaller priority set in the next plan reserves capacity for continuation pages; full capped pages remain incomplete. |
| Classification | Manufacturing/factory labels can hide headquarters and R&D at mixed sites. | Hold mixed sites for office-location clarification. Exclude proven manufacturing-only places, not every manufacturing company. Specific mapped corporate offices need no mandatory official-website verification. |
| Human review | Reject/held decisions are intentional decisions, not sampling gaps. | Lock all historical dispositions; recovered candidates never override them. |

| Pilot | Attempts / successful pages | Raw / unique POIs | First / second pages | Full pages | Original review rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 24 / 24 | 600 / 600 | 16 / 8 | 24 | 45 |
| 2 | 24 / 19 | 412 / 401 | 16 / 3 | 15 | 121 |
| 3 | 48 / 46 | 942 / 941 | 46 / 0 | 31 | 276 |

The 83 intersecting fine-grid cells contain 46 successful first-page samples,
36 with no fine-grid query, and one failed cell. Of the successful cells, 31
returned a full page. Earlier coarse queries overlap these areas; grey means
**no successful fine-grid query**, not never sampled at any resolution. No cell
is classified as verified empty or complete. AMap's current
[official search documentation](https://lbs.amap.com/api/webservice/guide/api-advanced/newpoisearch)
says pagination is not a full-inventory guarantee; v5 response `count` is the
current response's returned count, not total inventory.

All 145 approved locations reconcile to original provider coordinates and exact
reach membership: zero mismatches. Maximum GCJ02→WGS84→GCJ02 round-trip error is
1.5284e-11 degrees. Cached points fit their requested rectangles within the
diagnostic tolerance. The observed deficit is primarily discovery/sampling and
exclusion logic, not evidence of an empty office district or a conversion offset.

## Recovery result and missing-company trace

**291 previously unreviewed candidates**, all pending: 244 originally excluded
outside Pilot 2's 10-minute scope and 47 excluded by the category gate. Zero
cross-snapshot provider-ID conflicts. Historical IDs are excluded before
recovery; same-name/address or related-campus risks are held, not fuzzy-merged.

| Representative target | Actual trace | Next action |
| --- | --- | --- |
| SMIC / 中芯国际 | No matching name in any of the three raw caches. It was never returned, rather than rejected by a human. Its exact category omission cannot be inferred. | Source-backed name search and a reliable office POI/location; do not invent coordinates or claim exact 30-minute inclusion. |
| 芯原 | Returned in Pilot 2; outside 10 but inside exact 20/30. | Recovered pending. [Official HQ/Shanghai office](https://www.verisilicon.com/cn/ContactUs) matches 春晓路289号20楼. |
| 华虹 | Returned in Pilot 2; outside 10 but inside exact 20/30. POI address is a road-junction offset. | Pending exception. [Official group address](https://www.huahong.com.cn/?id=62&m=channel) is 碧波路177号A区4楼; precise POI/building correspondence remains unresolved. |
| 环旭电子 | Returned in Pilot 3 with factory + company codes, rejected by the old category parser; inside exact 30. | Pending mixed-site exception. [HQ](https://www.usiglobal.com/cn/company-profile) and [Zhangjiang R&D/manufacturing site](https://www.usiglobal.com/cn/global-locations?location_id=usi-shanghai-zhangjiang-china) share 张东路1558号. A campus point does not locate its office building. |
| 朝阳永续 | Company + service codes rejected by category parser; inside exact 20/30. | Recovered pending. [Official contact address](https://www.go-goal.com/contact-us) matches the POI building/floor. |
| SAP, NVIDIA, Dow | Already approved, used as positive controls. | Preserve approval; do not rediscover or change identity. Another SAP campus POI is separately held for duplicate-risk review. |

SMIC's [official 2023 annual report](https://www.smics.com/uploads/66152426/688981.pdf)
lists 张江路18号 as an office address in indexed public text. Direct retrieval was
restricted, and this historical disclosure does not verify current occupancy or
the office entrance. The historical reference image and park event reports are
discovery leads only, never current occupancy evidence. The marked screenshots
were unavailable in this execution; the four priority cells use measured cache
gaps and must not be represented as the user's marked boundaries.

The selected eight-target benchmark contains seven located within exact 30
minutes: three already approved and four recovered pending. SMIC remains
unlocated and is excluded from the spatial denominator. This small, selected
benchmark is a regression aid, not a Shanghai-wide recall estimate.

## Review experience and confidence

The existing Console preloads the recovered batch with **37 credible suggestions,
8 suggested exclusions and 246 exceptions**. Six candidates carry targeted
public-source or duplicate-risk annotations. The other records were not all
externally verified. Five exceptions are priority cases. Every new row remains
pending until a named human explicitly confirms it.

1. Open `company-review.html`, then **覆盖诊断与缺失公司追踪** to inspect grid
   states, company omission stages and evidence limitations.
2. Fill **审核人**. Select **可信候选 → 抽查本组（最多 8 条）**. If satisfied,
   choose **批量确认接受**, read the full target count, acknowledge and confirm.
3. Select **建议排除 → 抽查本组 → 批量确认排除** after checking the group.
4. Select **重点核实 → 只看关键例外** for the five priority cases. Unresolved
   remainder can stay pending or use **整组标记待核实**; no need to decide every
   ambiguous location individually.
5. **导出决定与历史** produces one JSON for trusted validation/import. CSV is
   optional. No bulk action overwrites a decided or locked row. The map stays at
   145 approved offices until a validated human import is published.

Acceptance remains `reviewed mapped office` (canonical confidence `building`).
Public evidence informs review, but does not silently upgrade any record to
`verified physical office`. Corporate manufacturing/R&D activity is not itself
an exclusion. Mixed-campus evidence requires locating the office component.

## Reproduce and import

```sh
node scripts/company-access/discovery/workflow.mjs prepare \
  APPROVED_145_ROOT EVIDENCE_INPUT_JSON \
  offline-output/company-access/FRESH_RECOVERY

node scripts/company-access/build-review.mjs \
  APPROVED_145_ROOT offline-output/company-access/FRESH_RECOVERY

# Only after a human returns the exported Console session:
node scripts/company-access/discovery/workflow.mjs import \
  APPROVED_145_ROOT HUMAN_SESSION_JSON \
  offline-output/company-access/FRESH_APPROVED
```

The importer rebuilds trusted pending/history bundles from the original
snapshots/ledger, validates decision history and locks, and sends accepts alone
through unchanged Phase 2 ingestion and merge. A change to any prior canonical
office fails closed. Rejected, held and pending decisions plus original source
provenance remain audit-only. Imported recovery bundles become locked history
for subsequent batches. Real snapshots, pending bundles and evidence JSON stay
outside git. The four existing canonical frontend artifacts are unchanged.

## Next targeted discovery plan — staged, not executed

`discovery/plan.mjs` emits a deterministic hashed plan only; it is **not an
enabled acquisition runner**. Do not dispatch the exhausted Pilot 3 workflow to
run it or reset the old checkpoint. The next execution needs a distinct reviewed
plan/checkpoint binding in the existing manual GitHub Actions infrastructure,
using the same `JINKE_AMAP_KEY` and shared AMap client.

- Split each selected parent cell `r10c7`, `r10c9`, `r11c8`, `r11c9` into four
  finer cells, intersect with exact 30-minute geometry. These priorities are
  provisional measured gaps, pending reconciliation with the marked screenshots.
- Sixteen spatial streams use `170000|141100` for broad corporate/research
  discovery. Three source-backed Shanghai-limited name streams target SMIC,
  华虹 and 环旭; they omit category restrictions. 芯原's matching cached office
  needs no new request. Name matches never merge identities or invent aliases.
- Nineteen first-page streams leave budget for later pages. Request page N only
  after a successful full page N−1, keep saturated capped streams incomplete,
  and split them in a separately reviewed plan instead of scraping to a target.
- Proposed cap: 48 lifetime attempts, 24 per execution, 25/page, at most three
  pages/stream, one retry, 1500 ms pace, 3000 ms retry, 300 pending candidates.
  Reserve attempts before I/O; retain every success/failure; skip completed and
  retry-exhausted queries; reuse the cross-cell connectivity circuit breaker.
  These are future bounds, not added attempts on Pilot 3.
- Corporate contact/office pages provide named address leads. Official park
  tenant directories provide company/building leads with dates and source URLs.
  Historical park news/images nominate targets only. Geocoding/POI identity and
  exact reach validation precede a pending Console row; a park is not a company.
- Require per-cell request/page/full-page statistics, source contributions,
  provider-ID conflicts, exact clipping, historical-decision matches, benchmark
  stage traces and source dates in every future batch. Separate newly sampled
  area from newly returned POIs and newly human-approved offices.

Before 30–40/40–50 discovery, resolve or document the benchmark gaps, inspect
the 30-minute unsampled/saturated cells, and validate the next bounded plan's
checkpoint runner. Process outer bands separately with disjoint geometry,
independent checkpoint budgets and the same locked-history review/import gate.
No broader acquisition is enabled by this change.

## Validation and invariant boundaries

134 JavaScript tests cover old snapshot compatibility, multicode discovery,
cached 10→30 recovery, invalid coordinates/conflicts, deterministic input order,
human-only import, canonical validation, history preservation, manufacturing/R&D
triage, coverage states, bounded planning, bilingual search, individual point
clicks, basemap lifecycle and economic guards. Real pending-only import must
produce zero new approved offices. Python/model files and general location
search are unchanged; Python tests were not rerun (pytest unavailable).

Core+ 50-minute employment stays exactly **1,212,066.713237**, Shanghai share
**37.6335253%**. Company counts never enter these calculations. Existing 156-file
economic hashes are guarded. Normal builds exclude real data and the Console;
only explicit review packaging contains this pending batch. The development
server now honors the preview supervisor's `--port`; runtime behavior is unchanged.

Browser checks confirm bilingual results, locked history and pending group
counts. This test browser disables WebGL, so live map rendering is unverified;
the Console now explains this gracefully while retaining list/evidence/export.

Existing Review Site: https://jinke-pr19-review.wuyifan88888.chatgpt.site
PR: https://github.com/FelixVVu/jinke/pull/20 (draft, unmerged).

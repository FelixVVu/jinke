# Targeted 30-minute artifact review — 2026-10-24

Review-only analysis of the user-supplied `company-access-targeted-30-v1-40071080444(1).zip`. No acquisition, acceptance, canonical import or production deployment occurs in this change.

## Reconciliation

The checkpoint validates against its immutable plan and payload hashes. All 300 artifact rows and normalized records reproduce from that snapshot. Its 19 successful attempts returned 366 observations / 360 unique provider IDs. Six repeated observations, 16 known IDs, 30 outside-30-minute records, five out-of-provider-scope records and nine candidate-cap overflow records remain in the original audit. There are no provider conflicts or invalid-coordinate exclusions. The nine overflow candidates remain in the cache/audit, outside the 300-row review batch.

All 300 candidates remain pending. Suggestion groups: **38 trusted candidates** (three public address matches and 35 consistent mapped office records), **15 suggested exclusions**, **247 exceptions**. Eight candidates have individually bound public evidence. The others were classified from provider name, address, category and relationship flags; no claim of externally verifying all 300. Human confirmation remains mandatory, and confidence remains reviewed mapped office unless independently verified by the existing canonical methodology.

The 145 approved offices, their four frontend artifacts, 442 historical decisions and 291 recovery candidates retain their original values. The hashed baseline is recomputed and compared before release. The browser receives only review rows, compact evidence annotations and diagnostics; provider snapshots and raw caches stay offline.

## Precision rules and representative companies

The targeted batch has an explicit `TARGETED_PRECISION_V1` seed. It excludes parking, charging, civil-defense infrastructure, named restaurants/canteens, car servicing, construction project offices and property service points. Mixed company/store categories are held for review, not blanket-rejected. Building/campus points are held separately from company-office records. Exact shared-unit or suspected brand/entity relationships flag exceptions and never merge identities. These new rules do not change original recovery suggestions or human decisions.

- **SMIC:** principal gate/address POI and a building POI discovered. SSE lists Zhangjiang Road 18; historical HKEX disclosure describes office and production buildings. This does not establish the gate or SO8 building as an independently confirmed current office. Canteen, parking, charging and other facilities are distinct noise records.
- **Huahong Grace:** official pages list Halei Road 288 as both China headquarters and Fab 2. Two same-name/address POIs require duplicate resolution. Zuchongzhi Road 1399 is listed as Fab 3; specific office/R&D use there is not established. Huahong Group is not merged with Huahong Grace.
- **USI:** official Zhangjiang facility description supports R&D plus manufacturing at Zhangdong Road 1558. Its principal POI is already in the 291 recovery queue; the new building point is held as a relationship exception, not an additional office.
- **AMD / OMNIVISION:** current official location pages provide address leads, but the artifact returned no matched POIs. Addresses alone cannot establish exact 30-minute membership. These are unresolved discovery gaps, not zero-office claims.
- **Baosight, Roche R&D, DuPont:** official headquarters/R&D address evidence supports specific pending POIs. This does not change canonical names, fill missing building fields, or automatically verify physical occupancy.

Source URLs, observation dates, POI/address bindings, scope and limitations are embedded in the private evidence pack and Console details. The historical reference image remains a prioritization aid, not occupancy evidence.

## Coverage and safe continuation

All 16 finer cells have a first page; ten are full and incompletely paginated (two northwest, four east, four south). Six short first pages terminate their provider query only. None is verified empty or inventory-complete. SMIC and Huahong name streams are also full; USI's name stream ended with four results.

The priority footprint is approximately 3.14 km² of a 50.22 km² 30-minute reach (planar diagnostic estimate, not geometry membership). Areas outside these four priority regions remain outside this campaign's fine-cell sampling. Name-hit recall is 4/6 representative targets; this is not confirmed-office recall. No new office has been approved.

`continuation-plan.json` pins the original snapshot/plan, 19 spent / **29 remaining** lifetime attempts, all cached queries and failed-attempt history. It identifies page 2 for ten geographic cells before the two noisy name streams, retains nine cached overflow IDs, and proposes official-source-backed AMD/豪威 searches. Short-page/completed queries are never reacquired. These proposals require a versioned child plan with shared parent accounting; they are not executable mutations of the immutable campaign.

**Execution is deliberately disabled:** the original 300-candidate cap has been reached. Running the existing workflow again returns zero useful requests. Suggestions do not delete candidates or release capacity. Before any more provider calls, a separately validated capacity policy must preserve every candidate and prove a bounded review workload without increasing the original 48-attempt quota. No workflow/quota/checkpoint was reset or enlarged by this change.

## Reproduction and Console behavior

Run `scripts/company-access/discovery/targeted-review.mjs` with the extracted artifact, preserved recovery directory, reviewed evidence annotations, original readiness JSON and a fresh `offline-output/company-access/...` directory. It validates and reproduces the snapshot before generating the targeted bundle, evidence pack, full analysis, continuation plan, composite bundle and verification manifest. Real records and evidence packs are not committed to git.

The review build accepts this output directory as its fifth CLI argument, after the original approved root, recovery root and readiness JSON. The normal build remains unchanged. The Console appends the targeted batch to the preserved history/recovery queue and defaults to the new 300-row batch. Sampling and bulk confirmation are scoped to the selected batch. Search remains bilingual and spans history; each batch can still be selected independently. Re-appending/reloading prefers a validated saved composite draft over a fresh pending migration. Human decisions and notes are never initialized from suggestions.

Suggested user workflow: fill reviewer → keep `targeted-30-v1 · 300 条` selected → `可信候选` → `抽查本组（最多 8 条）` → only if satisfied, `批量确认接受` and explicit acknowledgement. The other 262 records may remain pending. No need to inspect 300 rows or handle CSV. Export a single session JSON only when decisions are ready for validated import.

## Validation

156 JavaScript tests pass, including six new behavioral tests for facility noise, manufacturing/R&D distinctions, deterministic all-row analysis, bounded continuation, batch isolation and saved-draft preservation. Existing SAP/NVIDIA, point click, basemap lifecycle, canonical schema and exact employment guards remain passing: **1,212,066.713237** and **37.6335253%**. Approved frontend bytes and the historical/recovery baseline match exactly. Python tests could not start because this runtime lacks `pytest`.

The managed local preview stopped before browser navigation completed; local visual QA was unavailable. This is a preview infrastructure limitation, not a reason to alter application code. Hosted review verification is recorded separately after publication.

# Pilot 3: geographic coverage and JSON review handoff

Scope: existing PR #20 and existing review Site only. No production change,
location-search change, automatic acceptance or 40/50-minute acquisition.

## Initial implementation validation (2026-10-13)

108 JavaScript tests pass, including reservation/resume ceilings, checkpoint lookup
failure gates, exact geometry, historical locks, human bulk decisions, canonical
deduplication, safe artifacts, existing interaction/alias tests and economic guards.
A separate file-level mock run used the actual 104-office / 166-decision baseline:
one synthetic human accept passed the CLI and review build; every baseline feature
and decision remained identical. Synthetic outputs are ignored and never deployed.
The deployed review build continues to use only the real approved 104-office data.
No new real acquisition or real end-to-end review is claimed. Real Pilot 3 requests,
candidates and new review workload are currently zero, pending manual dispatch.
Python tests were not rerun (pytest unavailable); no Python/model files changed.
Live browser QA was unavailable; publication and build validation are separate checks.

## Fixed acquisition policy

- Exact existing cumulative 30-minute reach; 16×16 bounding grid, retaining only
  the **83 cells intersecting the polygon** (using the existing polygon-clipping library).
- Prior Pilot 1/2 snapshots produce aggregate observations per new query rectangle.
  **54 cells have no prior POI observations**; these lead the schedule. This is a
  sampling gap, not evidence that a cell has no offices, and is not a claim that
  coarse earlier queries never touched it. No company identities enter this aggregate.
- Order: zero observations, then 1–3, then >3. Within each tier, choose cells farthest
  from already scheduled cells; stable ID breaks ties. First pages across cells
  precede second pages. Exact clipping alone controls candidate inclusion.
- Existing category 170200, 25 POIs/page, at most two pages/cell, **48 lifetime attempts**
  including retries, **24 attempts per manual execution**, **300 candidate cap**,
  1500ms pacing / 3000ms transient retry delay, at most one retry/query.
- Shared AMap client and existing GCJ02→WGS84 conversion; same JINKE_AMAP_KEY.
  Quota/auth failures stay stopped. No target-count scraping or expanding the budget.

Even an error-free, uncapped 48-attempt run can sample at most 48 of 83 cells,
leaving at least 35 for a separately reviewed future plan. Retries and the candidate
cap can leave more. The plan intentionally does not claim complete coverage.

## Recovery after run 38557699693 (2026-10-14)

The second execution's original artifact validates at 26/48 lifetime attempts:
24 cached responses, two retryable AMAP_NETWORK failures on one query, and 104
pending candidates. The original snapshot is retained unchanged. This is separate
from the 104 previously approved offices and 166 historical review decisions.

The recovery fix derives state from the existing append-only attempt ledger:

- A query with two retryable failures has used its one retry. Skip it permanently
  for this pilot, record RETRY_EXHAUSTED with its cell/page/query ID, and continue
  to the next eligible query. Cached successful pages are never requested again;
  a failed first page never causes a second-page query.
- Coverage artifacts mark the cell incomplete, including when another page in that
  cell succeeded. Snapshot/QA record every original failure and incomplete query.
  Incomplete coverage is never described as an empty office area.
- Four consecutive retryable transport failures (AMAP_NETWORK or HTTP 5xx) spanning
  at least two distinct cells trigger AMAP_CONNECTIVITY_STOP. A successful response
  resets that streak. The streak is derived across executions, so a restored open
  circuit makes zero further requests. Inspect connectivity before any recovery;
  no automatic reset, health probe, fresh quota or retry allowance is added.
- Non-retryable quota/auth/provider failures remain sticky. Unknown interrupted
  attempts remain counted and skipped. The fixed plan, pacing, candidate cap,
  24-per-execution ceiling and 48-lifetime ceiling are unchanged.

The next manual dispatch can use at most **22 remaining attempts**. If connectivity
has recovered, it skips the exhausted query and samples other cells. If the next
cell also fails both attempts, the cross-cell cutoff stops at 28/48 lifetime attempts.
Use a fresh Run workflow on review/company-access-scaffold, not Re-run jobs. Keep
the latest artifact even if the job reports a connectivity failure.

Validation: 113 JavaScript tests pass, including the 26-attempt checkpoint shape,
isolated failure recovery, cross-cell network/HTTP-5xx cutoff, sticky cutoff on
resume, partial retry allowance, success resetting the streak, fatal provider
stops, original cache/ledger preservation, and incomplete-cell reporting. Replayed
the exact run 38557699693 artifact with mocked responses: cell r12c5 was skipped,
all 24 responses and 104 pending candidates were preserved, and healthy transport
used exactly the remaining 22 attempts. A mocked continuing outage stopped after
two new attempts at 28/48. Zero real AMap calls were made during this validation.
Existing model/result and review-decision regression guards pass. No new data was
accepted, committed or deployed; the existing review Site remains unchanged.

## Manual Actions execution and checkpoints

Use existing `company-access-amap-pilot.yml`, select `review/company-access-scaffold`,
then Run workflow. The default-branch Actions display name may still say Pilot 2;
the branch's run is titled **Company Access AMap Pilot 3 (manual review only)**.
No new workflow registration or main-branch update is needed if this previously
used manual workflow remains registered.

The GitHub-only resume step uses the ephemeral Actions token to locate the latest
earlier Pilot 3 run on this branch and restore only its fixed snapshot ZIP member.
It refuses a missing/expired checkpoint, incomplete prior run, or unverifiable
history instead of silently starting a fresh quota. AMap credentials are present
only in the acquisition step. No input permits arbitrary polygons, provider URLs,
keywords or quotas. Artifacts expire in 30 days; retain the downloaded ZIP.

If the summary says **EXECUTION_BUDGET**, manually run the same workflow again to
resume. Cached responses are reused and lifetime attempts cannot exceed 48. Stop
running when REQUEST_BUDGET, CANDIDATE_CAP or PLAN_COMPLETE is reported. Do not use
GitHub's Re-run jobs; the existing rerun gate rejects it. Provider stops require
inspection, not repeated retries. An interrupted request is reserved in the local
snapshot before network I/O; it is counted and never blindly repeated on resume.
If the job dies before uploading an artifact, the next run blocks for recovery.

The current session has no callable dispatch operation or authenticated gh CLI.
No real Pilot 3 run has been claimed; actual API requests/candidates are zero until
the user starts the workflow. An inaccessible registered workflow is a blocker,
not authorization to edit main or add an automatic push trigger.

## What to do in the Review Console

1. Finish the bounded acquisition/resume before reviewing. Download the **latest**
   `company-access-amap-pilot-3-RUN_ID` artifact and extract it.
2. Open the existing Review Console and choose **Open new batch** →
   `review/review-bundle.json`. No CSV editing is required.
3. Enter your reviewer name. Keep **New candidates only**. Existing 166 decisions
   are overlaid from the deployed history and locked, including repeat provider IDs.
4. Filter by suggestion/reason, inspect map/address/evidence, and use explicit
   Accept / Reject / Needs review. Bulk actions affect selected editable results;
   nothing is automatically accepted. Ambiguous cases may stay pending or be held.
5. **Export decisions & history**. Send that one session JSON plus the latest
   acquisition ZIP back for validated import. Draft recovery is browser-local;
   the exported JSON is the durable handoff. Keep the snapshot and decisions together.

Amber cells have no prior observed POIs, grey have prior observations, green have a
successful Pilot 3 page. Cell geometry is clipped to reach. These are sampling
categories, not employment estimates or inventory completeness. Candidate points
remain individual MapLibre layers; no DOM markers. New workload and remaining
pending count appear above the queue. Aliases/search and existing bulk tools apply.

## Validated import and review map

```sh
node scripts/company-access/amap/pilot3-workflow.mjs import \
  BASE_APPROVED_DIRECTORY \
  LATEST_ARTIFACT/provider-cache/snapshot.json \
  EXPORTED_SESSION.json \
  offline-output/company-access/pilot-3-approved
npm run company-access:review-build -- offline-output/company-access/pilot-3-approved
```

This one command reconstructs the trusted incoming/history bundle, verifies every
decision and edit history, imports explicit accepts using unchanged Phase 2 rules,
excludes repeat historical IDs from new records, merges with the original inventory,
and preserves all historical decisions. It blocks any merge that changes a prior
canonical office feature. New duplicate/conflict/quarantine dispositions and human
accept counts are reported. Needs-review/rejected/pending rows remain in the ledger
and audit session but do not become offices. Reviewed mapped offices do not become
verified physical offices without strong evidence.

The result retains original snapshots, the full session/history, canonical/audit
outputs, import QA and the combined decision ledger. Review packaging loads only
canonical accepted offices into the existing map; no browser decision directly
publishes data. Deployment to the existing review Site is a separate authenticated
step, already authorized by this task. No raw evidence/credentials enter normal UI.

## Next bands: gated strategy, not activated

After real Pilot 3 decisions and map reconciliation pass, create independent fixed
plans for `(40-minute polygon minus 30-minute polygon)` and then `(50 minus 40)`.
Use exact geometric differences (including non-nested slivers), stable smaller cells,
first-page spatial spread, measured new-candidate yield, duplicate rate and manual
review backlog. Carry prior decisions and sampled-cell/page history forward; sample
untouched cells before revisiting full pages. Keep each separately approved batch
at 24 attempts/execution, a bounded lifetime budget and reviewable candidate cap.
Do not proceed while unresolved identity conflicts, provider quota errors, missing
checkpoints, or preservation regressions remain. Report cells sampled/remaining,
new vs known IDs, suggestions and decisions, exact clipped counts and rejection
reasons for every batch. Coverage and workload, not a target company count, determine
whether the next bounded batch is worthwhile.

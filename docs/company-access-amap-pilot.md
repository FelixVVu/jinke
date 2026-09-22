# Company Access: AMap pilot 1 (review only)

This adds controlled acquisition and human review to Phase 2. Identified office
candidates and reviewed office locations have **source-dependent coverage**.
Neither is a census, a verified physical-office register, or an employment/GDP
measure. No production loader is enabled. The 156-file economic/model baseline
is unchanged, including Core+ 50-minute employment **1,212,066.713237** and
Shanghai share **37.6335253%**.

## Existing runtime inspection and secret reuse

Inspected the actual Site source attached to saved version 32, commit
`5899143c7e25c61ed0b394c9b29084b234dbeb0d`:

- `hosting/app/api/location-search/route.ts` re-exports the AMap route.
- `hosting/app/api/amap-place-search/route.ts` imports `env` from
  `cloudflare:workers` and calls `searchPlaces(request, env)`.
- `hosting/server/map-runtime.mjs` reads **JINKE_AMAP_KEY**, calls
  `https://restapi.amap.com/v5/place/text`, and returns a limited POI field list.
- The Worker uses `nodejs_compat`. Its manifest has no D1 or R2 binding.
- Sites configuration confirms the one AMap value is a protected secret;
  the read API returns its value as null. No value was retrieved or printed.

The GitHub branch did not contain this hosting wrapper. This PR brings over
only the two existing routes and runtime handler, then extracts their transport
into `hosting/server/amap-client.mjs`. The private pilot job and interactive
search share that client, the same binding, 12-second timeout and fixed AMap
origin. Redirects are refused. Errors contain local codes, never request URLs,
provider error bodies or credentials. Successful payloads are checked for a
credential echo before caching. The remaining hosting application stays in the
existing Site source; this PR does not create another app or change its build.

This is a reviewable integration patch, **not an already activated production
change**. No public acquisition route, new secret, scheduled task, or production
source push was created. These modules are never imported by `web/src` or copied
by the static build.

## Files and processing flow

```
hosting/server/amap-client.mjs       shared server transport
hosting/server/map-runtime.mjs       existing interactive handler, refactored
hosting/server/company-access-job.mjs private callable Worker job
hosting/app/api/{amap-place-search,location-search}/route.ts existing routes
scripts/company-access/amap/
  plan.mjs                          fixed 30-minute query plan
  acquire.mjs                       bounded acquisition, cache, clipping, mapping
  review.mjs                        CSV, decisions, canonical rebuild, QA
  files.mjs                         offline export/import CLI (no credentials)
tests/company-access-amap.test.mjs   mocked provider tests only
```

The committed five-polygon reach artifact is the source of truth. The job pins
its canonical JSON SHA-256 to
`2e1b01d4d7b70437836458dbb0b219e823d1bea582b692c4ab57b4c4d60306c7`.
Its actual 30-minute bbox is subdivided into 4 × 4 cells. Cell edges are sampled
and converted with Jinke's existing WGS→GCJ helper; their GCJ bounding rectangles
receive 0.0001° padding. This padding affects candidate retrieval only. Every
returned point uses Phase 2's existing GCJ→WGS helper and the exact cumulative
30-minute containment implementation. Bbox inclusion is never reach membership.

The narrow initial provider filter is `170200` (company category and returned
`1702xx` subtypes). Factory, consumer, residential and generic office-building
POIs are not intentionally requested. Provider classification remains separate
from Jinke industry classification. A company POI can still be an unsuitable
office candidate: the reviewer must assess it. Broader financial/professional
service categories are deferred instead of querying retail branches by default.

Policy is fixed in code and recorded in each snapshot:

| Control | Pilot 1 |
| --- | --- |
| Grid | 16 cells, south-to-north / west-to-east |
| Pagination | Page rounds across cells, at most 3 pages/cell |
| Page size | 25 |
| Request budget | 24 attempts total per resumable run, including retries |
| Pacing | 1,100 ms before a request; 2,200 ms before one retry |
| Retry | At most 1 for network failures or HTTP 5xx |
| Stop | HTTP 429, provider rejection, invalid response, exhausted budget |
| Candidate cap | 200 exact-clipped review candidates |

The request budget is intentionally smaller than the full plan. A full page
allows the next page; v5 `count` is the current page's count, not a total.
Successful pages are reused without calls, including empty pages. Fatal errors
remain sticky on resume; do not erase a failure ledger or create runs to bypass
quotas. Search weighting, the cell order and early stopping bias coverage.
100–200 accepted candidates is a review goal, not a guarantee: nobody is
accepted automatically and this code will not scrape until a target is met.

Provider documentation checked: [POI 2.0](https://lbs.amap.com/api/webservice/guide/api/newpoisearch).
This workflow records query parameters without the key; it does not assume the
provider returns an exhaustive inventory or that an account has batch quota.

## Cache, duplicates and provenance

The job returns a key-free snapshot and calls a supplied private `checkpoint`
after each completed attempt and at completion. Persist that checkpoint in the
existing runtime's private job/artifact facility before continuing. Serialize
one job per run: no parallel runs sharing the same snapshot. A process crash
between an upstream response and checkpoint persistence can repeat that last
request; completed persisted pages never need re-requesting. The production
Site currently has no private job/artifact facility, so enabling that facility
is an activation prerequisite, not something this PR silently provisions.

A snapshot contains the fixed plan, collected-at timestamp, successful raw
responses and hashes, lifetime attempt ledger, per-execution request/cache
counts, and stop reason. A replay validates the plan, hashes and request lineage.
No raw response is put in a browser artifact. Exact duplicate AMap IDs coalesce
with all query references retained. Conflicting name/address/coordinate/adcode/
typecode assertions for one ID are excluded as `POI_ID_CONFLICT`; no first-wins
merge. Different IDs with the same normalized name/address are flagged in the
review CSV, and the unchanged Phase 2 conservative spatial/address rules make
the final duplicate/conflict decision after human acceptance.

Invalid coordinates, invalid raw records, out-of-scope types, outside-30 points,
ID conflicts and over-cap records retain machine-readable exclusion reasons.
Raw provider fields, indoor parent/floor data and query lineage stay in private
JSON. An explicit returned `building_name` can be retained; an indoor parent ID
or floor alone is never turned into a building name. No automatic hub assignment
or industry inference is added.

Mapped raw records use `licensed_poi`, AMap ID, `GCJ02`, and
`source_evidence: {kind: 'map_poi', reviewed: false}`. `industry_code` and `sector`
remain null. Before review these records are quarantined by Phase 2. Acceptance
marks the **map evidence** reviewed, yielding `building` confidence, not
`verified`; `verified_at` remains null. Accept only a plausible mapped physical
office, not a registered-address-only or consumer POI. Use reject/needs_review
when that distinction cannot be established.

## Exact runtime action (not run or deployed)

The current environment cannot execute code inside the production Worker or
read its protected key. The existing public location-search route only accepts
text searches; it is not a secure batch execution API and was not repurposed.
**Real AMap Web Service calls made: 0. Unique real candidates acquired: 0.**

After this integration has been reviewed and an explicitly authorized existing
runtime job facility is available, invoke the following **inside that same
Worker**, with its existing `env` (not a copied key). `reachAreas` is the parsed
committed `web/public/data/reach-areas.geojson`; `previous` is the last persisted
snapshot or null. `persistPrivateSnapshot` is the private job facility's artifact
sink, which must be wired before activation; it is not an existing Site API.

```js
import { env } from 'cloudflare:workers';
import { runCompanyAccessPilot } from './hosting/server/company-access-job.mjs';

const result = await runCompanyAccessPilot(env, {
  reachAreas,
  collectedAt: '2026-09-22T00:00:00Z', // replace with the real acquisition start
  previous,
  checkpoint: persistPrivateSnapshot,
});
// Export result.snapshot as a private JSON artifact. Never serialize env.
```

Do not run this from a browser, add a public trigger, paste a key into a CLI,
or deploy merely to enable this task. This is the exact job call once the
private runtime invocation is available; there is no currently working remote
CLI command that can invoke undeployed code. The remaining activation is
explicitly blocked by the no-production-deployment constraint.

## Export for human review

With the privately exported snapshot available locally:

```sh
npm run company-access:amap -- prepare \
  --snapshot /private/path/amap-snapshot.json \
  --output offline-output/company-access/pilot-1
```

Outputs:

- `provider-cache/snapshot.json` and one raw response file per query hash
- `normalized/candidates.json` with provenance and exact converted coordinates
- `normalized/raw-input.json`, unreviewed Phase 2 envelope
- `review/amap-office-review.csv` and `.json`
- `audit/acquisition-exclusions.json`, `pilot-report.json` and `pilot-report.md`

All generated real data are under the existing ignored `/offline-output/`.
The CLI permits a fresh, single run directory under that root only, refuses
symlinks or existing output directories and never writes into `web` or `dist`.
Use UTF-8 CSV. Only edit `review_status` (`pending`, `accept`, `reject`, or
`needs_review`) and `review_notes`. Quoted commas/newlines are supported and
formula-like fields are escaped for spreadsheet safety. The importer checks
all IDs, row completeness and immutable fields against the snapshot; reordering
rows is fine. Do not change coordinates or source fields. Record substantive
corrections in notes for a later reviewed mapping pass.

## Rebuild approved pilot artifacts

```sh
npm run company-access:amap -- import-review \
  --snapshot offline-output/company-access/pilot-1/provider-cache/snapshot.json \
  --csv offline-output/company-access/pilot-1/review/amap-office-review.csv \
  --reviewer 'Your reviewer identifier' \
  --reviewed-at '2026-09-22T12:00:00Z' \
  --output offline-output/company-access/pilot-1-approved
```

Use the actual reviewer/time. Only `accept` enters `approved/raw-input.json`
and the unchanged canonical pipeline. Pending/reject/needs_review rows and
notes remain in `audit/human-review.json`; the source snapshot and reviewed CSV
are retained. Canonical conflicts/quarantines remain excluded even if a human
accepted the source row. Review acceptance count can exceed final office count.

`frontend/` receives exactly `company-offices.geojson`, `company-hubs.geojson`,
`company-reach-summary.json`, and `company-access-metadata.json`. `audit/` also
contains the existing three Phase 2 audit artifacts plus JSON/Markdown QA
reports with acquisition counts, failure/duplicate reasons, district/type
breakdowns, building coverage, decisions, canonical dispositions and exact
10/20/30/40/50 membership counts. No publication step is included.

## Validation and current pilot status

Mocked tests cover the shared server client/secret, absent configuration,
geometry pinning, cells/pages, pacing/retry budgets, successful cache replay,
provider errors, dedupe/conflict exclusions, conversion/exact clipping,
unreviewed quarantine, CSV integrity and decisions, reproducible canonical
rebuild, provenance and file separation. All existing lifecycle/schema/economic
tests remain required. Tests do not call paid or live AMap APIs.

Validation in this branch: **78 JavaScript tests passed, 111 Python tests passed,
static build passed, and diff checks passed**. The 156-file guard is unmodified.

No real review CSV or real inventory has been generated. The paths above are
output locations, not claims that a real pilot exists. The automated examples
use unmistakably synthetic names and credentials and remove their file outputs.
No second AMap key was created; no merge or production deployment occurred.

# Screenshot-priority 30-minute discovery — review only

Campaign `targeted-30-v1` is independent of Pilot 3. It never edits prior snapshots,
decisions or canonical offices. The frozen baseline is **145 approved offices,
442 historical decisions, 291 recovered pending candidates**. Only digests of known
AMap identities/assertions and approved name/address keys are committed. Real rows,
coordinates, decisions, notes, provider cache and new outputs stay out of git.

## Exact launch action

1. Open <https://github.com/FelixVVu/jinke/actions/workflows/company-access-amap-pilot.yml>.
2. Click **Run workflow**, select **review/company-access-scaffold**, then **Run workflow**.
   The workflow list may still show the old Pilot 1 name from `main`; the selected
   branch runs **Company Access targeted 30m v1 (manual review only)**.
3. If the stop reason is `EXECUTION_BUDGET`, launch another **new manual dispatch**
   on that same branch. Do **not** click Re-run jobs. The runner restores only this
   campaign's artifact and spends the remaining original quota.

No CSV review is required to launch. No secret needs entering: the acquisition step
alone receives the existing `secrets.JINKE_AMAP_KEY`. No other credential, provider
URL, keyword, rectangle, page count or budget can be supplied through dispatch.
No push/PR/schedule triggers, deployment steps or production runtime changes.

## Fixed plan and coverage interpretation

The current screenshot is aligned using the existing WGS84 station coordinates
for 金科路、张江高科、广兰路. Its four marked boxes (northwest, north-central,
east, south) receive 50 m alignment padding and a 2×2 subdivision each: **16 finer
cells**, interleaved across regions. Screenshot alignment is approximate and is
only a sampling priority. The historical company image is not authoritative current
occupancy or an address/coordinate source.

All four regions intersect the **unchanged exact cumulative 30-minute polygon**.
Spatial requests use corporate `170000` plus research `141100` categories, accepting
pipe-separated returned categories. Three source-backed text streams search
中芯国际、华虹、环旭电子 within Shanghai without a narrow category filter. Every
returned candidate still uses Jinke's existing GCJ02→WGS84 implementation, raw
validation and exact 30-minute clipping; an outside address is audit-only.

19 streams are paged round-robin: 25 records/page, maximum 3 pages/stream, next page
only after a full preceding page. AMap v5 `count` is not treated as a total.
57 possible page slots are constrained by **48 lifetime attempts**, **24 per run**,
one retry, **1,500 ms pacing / 3,000 ms retry pacing**, and **300 new candidates**.
The budget may expire before all full streams are paginated. Full capped pages
remain saturated/incomplete, never a complete inventory. A zero-result stream is
provider-pagination-exhausted, never verified empty.

All requests are reserved in an atomic checkpoint before network I/O. Successes,
failures and uncertain requests consume the lifetime budget. Exhausted queries are
skipped; four consecutive retryable connectivity failures across at least two
streams open a sticky circuit. Fatal provider/auth/quota failures are sticky. A
missing/expired checkpoint after acquisition started blocks a fresh run; recover
the artifact instead of resetting quotas. A provably skipped acquisition step can
be ignored. Keep artifact copies before the 30-day retention expires.

## Sources and identity boundaries

`targeted-leads.mjs` holds reviewable URLs, dates, address leads and limitations:
SSE/SMIC; Huahong's group/subsidiary contact directory; USI's corporate profile and
Zhangjiang R&D/manufacturing page; Baosight headquarters; AMD office directory;
OMNIVISION contacts; Pudong Software Park's incubated-company list.

Only the first three name streams make additional AMap requests. The remaining
official corporate/park sources supply a representative trace benchmark and future
location leads, not automatic tenant claims. No inferred coordinates, invented
aliases, name-based industry assignment or fuzzy entity merges. In particular,
华虹集团 and 华虹宏力/宏力二厂 are distinct identities/facilities; USI's mixed
R&D/manufacturing site is not rejected simply because it manufactures products.
Website evidence alone does not upgrade any candidate to verified physical office.

Known provider IDs are suppressed from new queues without altering prior decisions.
Changed assertions for known IDs are retained in audit as
`KNOWN_ID_CHANGED_REQUIRES_SEPARATE_REVIEW`. Conflicting new provider assertions
are quarantined. A different POI ID matching an approved exact name/address is
flagged for review, never auto-merged. All new review rows are **pending**.

## Outputs and Review Console

Download `company-access-targeted-30-v1-<run_id>` from the run. It contains only:

- `review/review-bundle.json` (single-file Console input), `amap-office-review.json`
  and `amap-office-review.csv`;
- `normalized/candidates.json`;
- `audit/acquisition-report.json`, `query-coverage.geojson`,
  `acquisition-exclusions.json`, `source-leads.json`;
- key-free `provider-cache/snapshot.json`.

A separate `company-access-targeted-30-v1-checkpoint-<run_id>` uploads even after
preparation fails. Both artifact types can resume the same campaign. Every payload
and output is checked for raw/escaped/encoded credential representations; no env
serialization or provider error bodies are logged.

On the existing Console, **打开其他批次** → choose `review/review-bundle.json`.
This appends new candidates, keeps the 291 recovery records, preserves local human
notes/history, and leaves all 442 historical decisions locked. Existing drafts
are backed up before appending. Changed assertions block the append for separate
conflict handling. The source report supplies per-stream pagination/failure gaps,
district/type breakdown and representative-name traces. Name-hit rate is explicitly
not identity-confirmed/spatial recall. The preflight panel retains the earlier
bound-identity benchmark; unlocated companies are excluded from its spatial denominator.

There is **no automatic canonical import** from this campaign. Later human decisions
must be validated against the immutable snapshot and prior ledger and pass the
existing canonical pipeline before any office enters the review map. No approval
work is needed at this discovery stage.

## Reproduce baseline preflight (zero provider calls)

```
node scripts/company-access/discovery/targeted-readiness.mjs \
  offline-output/company-access/pilot3-final-approved \
  offline-output/company-access/coverage-repair-release-20261023 \
  offline-output/company-access/targeted-30-v1-readiness-20261023
npm run test:frontend
```

The preflight reconstructs and exactly verifies the hashed baseline from private
archives, validates canonical outputs, counts prior coverage in each marked region
and emits a diagnostic footprint. It fails if any approved feature, decision,
pending row or source assertion changed. Packaging is explicit review-only:

```
node scripts/company-access/build-review.mjs APPROVED_ROOT PENDING_ROOT \
  TARGETED_READINESS_ROOT/targeted-readiness.json
```

Normal builds contain no real company inventory or Review Console data. Existing
economic guards remain exact: 1,212,066.713237 Core+ 50-minute employment and
37.6335253% of Shanghai. General location search is untouched.

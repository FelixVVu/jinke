# Reviewed Pilot 1 + Pilot 2 import

The user authorized import of the exact `company-access-pilot2-review-handoff.zip`
on 2026-09-27. Its original Actions artifact (run 36305000461), decision CSV and
review notes were retained. The notes call the classifications proposed; the
user's subsequent explicit import instruction authorizes these exact decisions
for the review dataset, not verified-office classification or production release.

Existing import-review and unchanged Phase 2 validation produced 76 Pilot 2
offices. The existing canonical cross-pilot merge combined those with all 28
Pilot 1 offices: 104 accepted, zero duplicates, conflicts, quarantines or canonical
rejections. No existing human decision was changed. Import attribution timestamp
is the user's authorization timestamp, not a claim about when review occurred.

| Reach | Pilot 1 | Combined |
| --- | ---: | ---: |
| 10 minutes | 0 | 76 |
| 20 minutes | 7 | 83 |
| 30 minutes | 28 | 104 |
| 40 minutes | 28 | 104 |
| 50 minutes / All | 28 | 104 |

Districts: Pudong 98, Huangpu 6. All 104 retain mapped-office (`building`)
confidence. Known hubs: zero. No building names or sectors were inferred.

Decision ledger: Pilot 1 28 accept / 9 needs_review / 8 reject; Pilot 2 76 accept /
36 needs_review / 9 reject. Combined: 104 accept / 45 needs_review / 17 reject.
The 62 non-accepted records remain in the source/review/audit package and are
excluded from browser GeoJSON. Raw source records and CSVs remain out of git.

Pilot 2 acquisition (from supplied artifact, no new calls here): 24 attempts,
including five network failures; 412 returned POIs, 401 unique IDs, 11 repeated
provider occurrences; 257 outside 10 minutes and 23 outside category scope;
121 review candidates. Stop reason REQUEST_BUDGET. These are bounded identified
office locations, never a completeness claim or employment estimate.

Reproduction, using fresh output directories:

```sh
node scripts/company-access/amap/files.mjs import-review \
  --snapshot offline-output/company-access/pilot-2-handoff/artifact/provider-cache/snapshot.json \
  --csv offline-output/company-access/pilot-2-handoff/amap-office-review_pilot2_proposed.csv \
  --reviewer 'Yifan (uploaded decisions, authorized import)' \
  --reviewed-at '2026-09-27T08:45:00Z' \
  --output offline-output/company-access/pilot-2-approved
node scripts/company-access/amap/merge-reviewed.mjs \
  offline-output/company-access/pilot-1-approved \
  offline-output/company-access/pilot-2-approved \
  offline-output/company-access/pilots-1-and-2-approved
npm run company-access:review-build -- offline-output/company-access/pilots-1-and-2-approved
```

Only the explicit review build loads this inventory. The existing dedicated
drawer, reach-filtered MapLibre clustering and basemap lifecycle are reused.
The review marker supports approved multiple-pilot imports while remaining
compatible with the prior Pilot 1 marker. Normal builds remain unconnected.
Location search, employment, heatmap and reach model are untouched.

Core+ remains exactly 1,212,066.713237 employment and 37.6335253% Shanghai share.
No merge or production deployment is authorized by this import.

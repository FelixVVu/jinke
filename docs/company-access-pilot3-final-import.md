# Pilot 3 final human-reviewed import — 2026-10-21

Used the user's exact `jinke-pilot3-review-import-handoff.zip`, containing
`company-review-session-9fae0e2a6736.json` and the run 38561610093 acquisition
artifact. The existing trusted `pilot3-workflow.mjs import` command was used
unchanged. No acquisition was performed.

The final human session, including individually approved exceptions, governs
acceptance. Automatic triage suggestions do not override it. Session/bundle
binding, all decision history chains and locked historical rows validated.

| Decision | Pilot 3 | Historical | Combined |
| --- | ---: | ---: | ---: |
| Accept | 41 | 104 | 145 |
| Reject | 36 | 17 | 53 |
| Needs review | 199 | 45 | 244 |
| Pending | 0 | 0 | 0 |
| Total | 276 | 166 | 442 |

All 41 accepts passed unchanged Phase 2 validation, coordinate handling,
normalization, conservative deduplication, conflict checks and exact reach
assignment. Duplicate collapses: 0. Conflicts: 0. Canonical quarantine or
validation exclusions: 0. Final inventory: **145 reviewed office locations**.
Every prior office feature and every prior decision/notes entry remains identical.

| Cumulative reach | Office count |
| --- | ---: |
| 10 minutes | 76 |
| 20 minutes | 84 |
| 30 minutes | 145 |
| 40 minutes | 145 |
| 50 minutes / All | 145 |

All retain mapped-office confidence (`building`); no automatic upgrade to
verified physical office, no inferred industry and no invented hubs. Hub count: 0.
Counts are source-dependent identified office locations, not employment counts or
a complete company inventory. The 40/50-minute counts do not imply acquisition in
those outer bands.

## Reproduction and retained audit

```sh
node scripts/company-access/amap/pilot3-workflow.mjs import \
  APPROVED_104_BASE PILOT3_SNAPSHOT FINAL_HUMAN_SESSION \
  offline-output/company-access/FRESH_IMPORT

node scripts/company-access/build-review.mjs \
  offline-output/company-access/FRESH_IMPORT
```

The original final session is preserved byte-for-byte in
`source-imports/pilot-3/review/original-human-session.json`. The normalized full
session/history is retained in `audit/pilot3-review-session.json`, all 442
decisions in `audit/human-review.json`, and all prior source snapshots/audits are
retained. Non-accept decisions remain excluded from canonical offices.

The explicit review build loads the 145-office inventory and publishes a Console
bundle with all 442 imported decisions locked. It contains no stale pending-only
Pilot 3 bundle. Raw snapshots and full ingestion audits stay out of browser assets
and git. The separate archived import package retains them for future imports.

Input SHA-256:
- Handoff ZIP: `6ac99b50697c2d3312d9227677368a6cd1fe86205f0e945834fa91771676ef0e`
- Original session: `4262ce986889c7c97485d7e43cf89f604c0eb6e965538397f5d40adaf3b7aa96`
- Exact snapshot bytes: `8ab6095860af56a500335890513ad5543cb4697701daf2d123c8e7fe405da529`

## Verification

- 123 JavaScript regression tests passed.
- Real import reconciliation: 41 accepts; 36 rejects and 199 held records excluded;
  all 104 prior features and 166 historical decisions unchanged.
- Actual review loader reconciles all four artifacts and loads 145 offices.
- Built Console reconciles all 442 statuses and notes to the final decision ledger.
- Existing point-click, alias search, MapLibre basemap lifecycle and 156-file
  economic guards passed. Core+ employment remains 1,212,066.713237 and Shanghai
  share 37.6335253%.
- Review build and diff checks passed. Python suite not rerun because pytest is
  unavailable; no Python/model or application code was changed. Live browser
  visual verification was unavailable in this environment.

Existing Review URL:
https://jinke-pr19-review.wuyifan88888.chatgpt.site

No new repository/site/PR, real-data commit, main merge, production deployment,
recollection, changed review decision or acquisition quota increase.

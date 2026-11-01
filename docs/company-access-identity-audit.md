# Entity and location audit — 2026-11-01

No decisions, canonical names, coordinates or approved artifacts are changed. The current review queues contain 38 records matching the Huahong/Huali, SMIC, USI and OmniVision screening terms (including address-only mentions). All 38 reproduce their stored WGS84 coordinates exactly using Jinke's existing GCJ-02 inverse. This checks conversion consistency, not survey accuracy, currency or office occupancy. No new acquisition or geocoding was performed.

## Huahong findings

All 14 Huahong/Huali name-or-address matches were audited. The [official contact directory](https://www.huahong.com.cn/?id=62&m=channel) distinguishes the group at Bibo 177 Area A fourth floor, Shanghai Huahong Hongli at Halei 288 and Shanghai Huali at Liangteng 6. The [2017 factory directory](https://www.huahong.com.cn/?id=459&m=detail) identifies Fab 2 at Halei 288, Fab 3 at Zuchongzhi 1399 and Fab 5 at Gaosi 568. Historical factory evidence does not establish current office occupancy. The [2024 group disclosure](https://www.huahong.com.cn/?id=1541&m=detail) explicitly identifies the group office floor.

| POI / records | Finding |
| --- | --- |
| B0LA7UOCSL group | Raw GCJ-02 121.584533,31.207241 → WGS84 121.58032206403622,31.209446752830488; zero conversion residual. Approx. 469.6m datum shift is expected conversion, not evidence of a displaced office. |
| B0L0AKATD8 A building; B00150CD68 park | Group is 20.2m from A-building POI and 4.9m from park POI. This suggests a generalized park/building position, not proven intersection placement. Neither POI independently verifies the fourth-floor office. No correction is proposed without precise building evidence. |
| B0FFLEW84S / B0LGYH4ROD Fab 2 | Same company and address, different IDs, 211.6m apart. Possible duplicate campus representation, not two approved offices; retain both for review. |
| B0KA3ZQF8M Zuchongzhi 1399 | Different factory address but only 11.6m from the first Fab 2 POI. Address/location conflict; do not merge or relocate. |
| B0FFFPU5KX Huali east area | Provider says Gaosi 497. Official directory assigns 497 to the integrated-circuit R&D center, while Huali contact is Liangteng 6 and historical Fab 5 is Gaosi 568. Entity/site ambiguity, not permission to move to Liangteng. |
| B0FFG7LS50 / B0FFIPOCNK parking entrances | Same name/address, 8.4m apart; possible duplicates, already rejected and remain locked. |
| B001573ETL restaurant; B0L3ONXEVT construction project office | Ancillary/non-inventory places, despite company-type tagging on the project POI. Suggestion only; decisions unchanged. |
| B0FFG8HN0V, B0KDXBXH5E, B0KUKUIFZU tenants | Other companies mentioning Huahong park in addresses. No Huahong corporate affiliation inferred. |

SMIC's company/Gate 1 and SO8 building POIs are near-coincident but remain distinct unresolved assertions. Cafeteria, parking, charging, shelter and shops are ancillary facilities. USI's Zhangjiang factory and building 1 do not establish the separate Shengxia Road sales office. OmniVision company, campus, tower, tenants and parking retain separate records and locked decisions. Existing official source annotations remain accessible; this pass adds field/coordinate checks rather than claiming fresh external verification of each POI. No AMD-name POI was found by this screening; absence is an inventory gap, not proof of no office.

## Implementation and review

`identity-audit.js` produces read-only annotations. Official entity/address bindings require exact provider ID + name + address. Shared relationship search expands Hua Hong/Huahong to explicitly bound related entities without treating the relationship as a synonym or identity merge. Drawer results group by entity with separate cards and explicit addresses; unbound tenants/facilities remain independent. Console details expose raw/recomputed coordinates, residual, flags and links to nearby/possible duplicate records. Proximity alone never indicates duplication. Human decisions and confidence upgrades remain separate.

The audit is computed for the full review bundle and included only as annotations in the separate candidate search artifact. Nonaccept candidates never enter approved clusters or analytics. Raw snapshots and release data remain outside git. Tests cover conversion mismatch/missing fields, duplicates, immutable rows and English relationship search retaining distinct entities.

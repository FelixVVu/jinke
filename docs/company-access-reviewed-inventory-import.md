# November 3 reviewed-inventory import

Input: original human session SHA-256 `06a99db02c0fccaf6678724f3d6a970b9d75d5985e8646e0ecb905f844dd2c38`. Rebuilt all 553 new candidate rows from three original pilot snapshots and the retained targeted snapshot, validating the targeted continuation parent. Exact source rows, batch identities and the complete 1,274-record session/event chain reconcile. All 721 prior decisions are locked and unchanged.

Human choices: 530 Accept and 23 Reject. Validation disposition is a separate field, never a replacement human choice. 191 accepts enter canonical ingestion; 339 are quarantined. Final inventory: **398 offices** (207 unchanged baseline +191), all `building` / reviewed mapped office; none upgraded to verified physical office. No duplicate collapse in the imported output. Possible duplicates and conflicts remain quarantined. All 23 Reject remain excluded. All source snapshots and original/earlier human event ledgers are retained outside git.

493 accepts have empty notes: **155 pass** the independent mapped-office gate and **338 remain quarantined**. Of 37 annotated accepts, 36 pass and one is quarantined. Missing notes alone are not a rejection rule. AMap identity/category/location evidence plus explicit human acceptance may support reviewed mapped-office confidence; it never establishes verified physical-office confidence.

## Independent validation

Old triage suggestions do not authorize or veto import. Checks examine exact source identity, provider categories, address/building/unit specificity, conflicting public evidence, known entity/location flags, ancillary or factory-only indications, duplicates and raw GCJ-02 conversion. Manufacturing names alone are not excluded: an identifiable office unit can pass. Vague locations, facility-only assertions and unresolved evidence are held. Public evidence can support mapped office eligibility but cannot override a contradictory source or gate/duplicate flag.

All 553 raw-to-WGS84 conversions reconcile. Canonical Phase 2 handles normalization, dedupe, hub assignment and exact five-polygon membership without modification. Incoming canonical conflicts are quarantined; any unresolved baseline change aborts release. Reach counts: **80 / 234 / 398 / 398 / 398** at 10/20/30/40/50. Counts are discovery inventory, not employment or completeness.

Quarantine primary reasons (each row counted once; additional reasons retained): office address detail 193; entity unresolved 119; provider use unresolved 13; duplicate/source conflict 5; store-vs-office 2; seven other evidence, facility, intersection or address conflicts. SMIC Gate 1/SO8, Huahong group, Hongli factory points, Huali east area and USI factory/building retain Accept where selected, but do not enter the map.

## Review experience and reproduction

Console records show **human accepted / validation quarantined / not mapped** separately, with reasons and a quarantine filter. Decisions remain locked. Quarantined accepts stay searchable as candidates using the separate selection ring; they cannot enter approved clusters/counts. Canonical search and economic models remain independent. Default builds contain no review inventory.

Run `node scripts/company-access/discovery/release-reviewed-inventory.mjs BASE SESSION FRESH_OUTPUT`, then `node scripts/company-access/build-review.mjs FRESH_OUTPUT`. Source snapshots must be available in BASE. Do not rerun acquisition. The retained handoff includes original bytes, per-record results, quarantine list, canonical artifacts and complete source/audit lineage. No real company artifact is committed to git.

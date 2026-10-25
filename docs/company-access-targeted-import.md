# Targeted 30-minute human import

The supplied `company-review-session-append_a86c9.json` validates against the source-rebuilt composite bundle: 38 new accepts, 262 targeted pending, 291 recovery pending, and 442 unchanged historical decisions. The complete event chains, notes and original provider snapshot are retained offline. Only explicit accepts enter unchanged canonical ingestion and cross-pilot deduplication.

Result: **183 offices**, including all original 145 byte-identical features. Zero duplicate collapses, conflicts, quarantines or rejected accepted-input records. Cumulative 10/20/30/40/50-minute counts: **79 / 100 / 183 / 183 / 183**. No known hubs are invented (hub count zero). Confidence remains reviewed mapped office.

The review release moves the 38 imported decisions to a separately keyed locked-history batch, retaining 480 historical decisions and 553 pending candidates. Both pending queues retain their source rows and evidence, with evidence-pack identities rebound and validated against the new history. The uploaded session remains unchanged as an audit artifact. Original 300-candidate acquisition cap/checkpoint and quota are unchanged; no new acquisition occurred.

`scripts/company-access/discovery/import-targeted.mjs` takes approved baseline, extracted provider artifact, recovery directory, human session, fresh output and targeted triage directory. It rebuilds both source batches, validates the complete human session and forbids edits to other batches. Canonical exclusions and any changed baseline office fail closed. Only non-pending explicit decisions become new history. Real files remain under ignored offline output, never git.

Review build inputs are the new approved root, its `review-pending` directory, `review-targeted/targeted-readiness.json`, and its `review-targeted` directory. The normal build still excludes real records. No production location search, economic model, main branch, API credential or acquisition workflow changes.

Validation includes source/session validation, full canonical and merge validation, repeatability, rejection of fabricated accepts lacking human history, mapped-confidence preservation, queue reconciliation and all existing economic/basemap/point-click/search tests. Economic constants remain 1,212,066.713237 and 37.6335253%.

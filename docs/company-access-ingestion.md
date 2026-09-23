# Company Access phase 2: offline preparation

This extends draft PR #20 on `review/company-access-scaffold`. It neither publishes data nor changes employment, GDP, density, basemaps or production reach polygons. All included company records are visibly synthetic test fixtures. No network calls, geocoding services, credentials, LLMs or new dependencies are used by the pipeline.

## Files and execution

| File under `scripts/company-access/` | Responsibility |
| --- | --- |
| `raw-schema.json`, `validate.mjs` | Separate raw record schema, strict runtime validation and dataset envelope |
| `normalize.mjs` | NFKC/whitespace normalization, conservative punctuation handling, district aliases, explicit name variants |
| `coordinates.mjs` | Existing AMap GCJ inverse reuse, BD-09 conversion, coordinate audit |
| `classify.mjs` | Evidence-based location confidence and reviewed industry eligibility |
| `dedupe.mjs` | Indexed identity/source grouping, conflict isolation, deterministic representatives |
| `hubs.mjs` | Reviewed building/campus assignment and optional spatial clusters |
| `ingest.mjs` | Pure raw-to-canonical orchestration, exact reach, seven outputs and reconciliation |
| `build.mjs` | Multi-file CLI, byte hashes, separate frontend/audit directories, guarded writes |
| `common.mjs` | Stable serialization, content IDs, distance and explicit settings |
| `benchmark.mjs` | Synthetic-only offline scale check against current reach polygons |

Other changes: `web/src/company-access/model.js` adds polygon bounding-box preselection while retaining existing exact containment and replaces per-hub full inventory scans with a membership map. `package.json` adds the CLI and test coverage; `.gitignore` excludes generated offline candidates. The economic regression baseline is unchanged. Tests and synthetic raw/coordinate/reach fixtures are in `tests/company-access-ingestion.test.mjs` and `tests/fixtures/company-access/`.

Run from the existing repository using Node 22:

```bash
npm run company-access:build -- \
  --input tests/fixtures/company-access/pilot.json \
  --output offline-output/company-access/pilot-run-001
```

`--input` may be repeated for multiple source files. Optional `--reach` defaults to the existing `web/public/data/reach-areas.geojson`. Optional `--settings` reads a JSON object. Use a fresh output directory for each run: existing output directories are never replaced. Inside this repository only descendants of `offline-output/company-access/` are allowed. Resolved symlinks into application/model/data directories are refused. Files are prepared in a staging directory and renamed only after successful validation. The build never copies candidates into `web/public/data` or deploys anything.

## Raw input contract

Each UTF-8 JSON file has this envelope:

```json
{
  "schema_version": 1,
  "dataset_kind": "synthetic",
  "dataset_version": "synthetic-pilot-v1",
  "records": []
}
```

A future real pilot uses `dataset_kind: "candidate"`, not `production`. All files in a run must agree on kind and version. The complete, runnable example is `tests/fixtures/company-access/pilot.json`; it is test data, not a source inventory.

| Raw field | Rule |
| --- | --- |
| `source_record_id` | Required stable nonempty source ID |
| `company_name`, `address` | Required nonempty text |
| `longitude`, `latitude` | Required keys; finite numeric coordinates or explicit null, which is rejected as unlocatable; numeric strings are rejected |
| `coordinate_system` | Required WGS84 / GCJ02 / BD09 / unknown; unknown is quarantined |
| `source_type`, `source_url` | Required canonical source type and HTTP(S) evidence URL; credentials in URLs rejected |
| `source_evidence` | Required object: `kind`, nonempty `description`, boolean `reviewed` |
| `collected_at`, `verified_at` | Required keys: valid UTC ISO time ending in Z; only verified_at may be null |
| `district`, `building_name`, `industry_code`, `sector` | Optional text or null; unsupported knowledge remains null |
| `source_namespace` | Optional stable feed namespace; default is source type plus URL host |
| `name_variants` | Optional explicitly supplied Chinese/English names; normalized and retained in audit, never automatically translated |
| `company_identity` | Optional reviewed relationship `{id, reviewed: true, source_url}` for the same legal entity across languages/sources |
| `office_identity` | Optional reviewed relationship with the same structure, specifically identifying one physical office |
| `classification_evidence` | Optional `{scheme, kind, source_url, reviewed}`; kinds are source_classification / reviewed_mapping |
| `hub_candidates` | Optional array of `{id, name, kind, source_url, reviewed: true}`; kinds are verified_building / mapped_building / reviewed_campus |

Unknown keys fail raw validation. A name alias alone is retained as provenance; cross-language deduplication additionally requires the reviewed identity relationship. Identity and hub IDs must be stable within a shared reviewed namespace. They are supplied evidence, not automatically discovered facts. `reviewed: true` means a source reviewer has checked the evidence; this offline code does not verify a website by visiting it.

## Processing flow

Raw envelopes → validate each record → normalize text and coordinates → classify evidence/industry → quarantine weak or ambiguous records → conservative deduplication → building/campus/optional cluster assignment → canonical schema validation → exact five-polygon reach assignment → derive/reconcile outputs → write separate frontend candidates and audits.

Batch configuration errors (invalid envelope, mixed dataset versions, bad settings or malformed reach geometries) fail the run without publishing partial artifacts. Individual invalid records go into the rejected output. Every raw occurrence receives a content-hash reference and exactly one terminal disposition: accepted representative, duplicate, conflict, quarantined or rejected. Counts must reconcile to the input row total. All duplicate sources remain attached to their accepted office, including original evidence, raw names and raw coordinates.

No current timestamp, random identifier or input iteration order determines analytical outputs. Exact input-file SHA-256 hashes are recorded in audit; a canonical sorted-record hash is also recorded, making semantic row-order invariance explicit. Changing raw file whitespace/order can legitimately change its exact file hash, even when canonical outputs are identical. Fixed files produce byte-identical artifacts across repeated runs and file argument ordering.

## Coordinate handling

WGS84 uses identity conversion. GCJ02 imports `gcj02ToWgs84` directly from the existing AMap search module; it does not duplicate or change that implementation. BD09 first applies the deterministic BD09-to-GCJ02 formula and then the same Jinke inverse. China-specific conversion outside its supported bounds is quarantined rather than silently treated as identity. Missing/nonfinite/out-of-range coordinates are rejected; unknown CRS is quarantined. There is no address-only geocoding fallback.

Audit retains `raw_longitude`, `raw_latitude`, `raw_coordinate_system`, `conversion_method` and `conversion_version`. The conversion version is pinned to `jinke-amap-iterative10-1e8+bd09-v1`. Fixed numerical fixtures protect WGS identity, the existing Jinke AMap transform and a conventional BD09 reference. They are numerical regression checks, not claims of surveyed positional accuracy. Global bounds alone cannot detect plausible but wrongly labeled coordinates; source CRS confirmation remains required before a real pilot.

## Confidence and industry methodology

| Evidence | Canonical confidence / default treatment |
| --- | --- |
| Reviewed official_office or official_recruitment from company_website, tenant_directory from building_directory, or government_office from government; verification time supplied | `verified`; accepted candidate |
| Reviewed map_poi from licensed_poi/osm or office_building from building_directory | `building`; accepted candidate |
| Registered-address-only, weak, unreviewed, mismatched source/evidence or missing required verification | `approximate`; quarantined by default |

`include_approximate: true` is an explicit offline option. If used, such offices remain marked approximate and counted separately in metadata; it does not upgrade evidence. No probabilities are invented. Evidence type and machine-readable classification reason are retained for each source.

Industry classification requires a reviewed `classification_evidence` with scheme `GB/T 4754-2017`. It admits the existing Core+ codes I, J, M, 721, 723, 724, 725 and four-digit descendants of the four approved numeric groups. For example 7210 retains its original code and maps to Core+ group 721. Code 726 is not included. Other coding systems or unreviewed classifications stay unknown; reviewed codes outside this explicit mapping remain as sourced codes with no Core+ mapping. Numeric divisions that would require an additional section crosswalk are not guessed. Provide an explicitly reviewed mapping into the supported codes when needed.

The canonical inventory can contain unknown/unmapped industries: Core+ office eligibility is separately recorded in audit and metadata. It never changes the Core+ employment denominator, employment estimate or heatmap. Company names are never used to infer industry.

## Duplicate and conflict rules

- Candidate groups use a namespaced source ID and, separately, an explicit reviewed office ID or `(reviewed company identity OR exact normalized company name, exact normalized address)`.
- Names retain legal suffixes. Normalization does not remove suite/floor numbers. Different addresses for one company remain separate offices. Different reviewed office IDs remain separate unless a reused source ID creates a contradiction.
- All members must be within `duplicate_metres` of a deterministically selected representative (default 15 metres). There is no chain of nearest-neighbour merges. Representative preference is verified → building → approximate, then known reviewed industry, latest supplied verification time, then stable record hash.
- Reviewed office identity can reconcile explicitly linked name/address variants at the same location. Other uncertain name variants, similar names or nearby points do not auto-merge.
- Conflicting source identity/address, office identities, coordinates, reviewed industry codes or district labels isolate the affected connected group. Reasons include SOURCE_ID_CONFLICT, CONFLICTING_OFFICE_IDENTITIES, LOCATION_CONFLICT, INDUSTRY_CONFLICT and DISTRICT_CONFLICT. Conflicts are not quietly resolved by selecting a preferred source.
- Duplicate review lists suppressed record references, retained office ID, representative reference and reason code. The ingestion audit retains every member source, so evidence is not discarded.

## Hub methodology

Per-office preference is verified physical building → reliable mapped physical building → reviewed named campus → optional unnamed spatial cluster → null. A bare building-name string is not sufficient for a reviewed hub. Ambiguous equal-priority IDs and inconsistent definitions of one hub are conflicts. Names come from the input evidence; no proper building/campus names are generated.

Output hubs carry `hub_kind`: `physical_building`, `named_campus` or `spatial_cluster`. Explicit IDs are type-namespaced. Spatial clusters are named only `Unnamed office cluster …` and have no invented building name. The spatial algorithm considers only unassigned, non-approximate offices. It processes stable office IDs in order, gathers unused offices within a fixed seed radius and requires a minimum count; it does not bridge a chain of nearby points. Three-dimensional spherical spatial buckets shortlist neighbours; final membership uses great-circle distance. Clusters may change when inventory membership changes and are not permanent property identifiers.

Default settings:

```json
{
  "duplicate_metres": 15,
  "include_approximate": false,
  "cluster_metres": 0,
  "cluster_min_offices": 2
}
```

Zero cluster radius disables algorithmic grouping. Allowed duplicate radius is 0–50m, cluster radius 0–250m and minimum cluster size 2–100. Actual settings, seed IDs, grouping reasons and source links are audited. Hub point geometry remains the phase-1 representative office position, not a surveyed building centroid. Reach statistics always count individual office memberships, never membership inferred from the hub point.

## Artifact contract

| Folder/file | Contents |
| --- | --- |
| `frontend/company-offices.geojson` | Canonical WGS84 offices and exact reach memberships; no raw evidence objects |
| `frontend/company-hubs.geojson` | Members/counts by reach, representative point and explicit hub kind |
| `frontend/company-reach-summary.json` | Five cumulative office/hub summaries |
| `frontend/company-access-metadata.json` | Versions, hashes, quality/coverage disclosures, settings, disposition and classification counts; explicitly offline/not published |
| `audit/company-ingestion-audit.json` | Accepted-office lineage, all source records/evidence, coordinate/normalization/classification/hub reasons, exact source-file hashes |
| `audit/company-rejected-records.json` | Invalid, quarantined and conflicting raw records with disposition/reason codes |
| `audit/company-duplicate-review.json` | Duplicate-to-office links and conflict groups |

Only four compact, precomputed frontend candidates are intended for eventual browser loading after a separately approved real pilot. Browser code must never receive the audit directories or perform geocoding, deduplication, classification or spatial joins. This phase adds no UI data loader and ships none of the test artifacts.

## Validation and scale

Tests cover raw validation, malformed/unknown CRS, fixed coordinate vectors, conservative normalization, bilingual reviewed identities, multiple offices per entity, evidence-based confidence, industry mapping, all duplicate/conflict dispositions, building/campus/cluster assignment, real reach thresholds, exact/unindexed containment agreement, tampered artifacts, file-order/byte reproducibility, multi-file ingestion and protected output paths (including symlinks). Existing MapLibre lifecycle and exact economic regression tests remain part of `npm run test:frontend`.

A synthetic-only 20,000-office / 20,000-hub run against the existing production reach geometries completed in **15.316 seconds**, with **606 MiB process RSS observed at completion** in this environment. This includes derivation and repeated reconciliation; it is an observed benchmark, not a maximum or SLA. Run `node scripts/company-access/benchmark.mjs 20000` to reproduce the workload. The pipeline deliberately loads inputs/audits in memory and is intended for offline tens-of-thousands scale, not streaming millions of records. Stable hash grouping avoids all-pairs deduplication; hub aggregation is indexed; reach bboxes only eliminate impossible polygon candidates.

Validation on the completed phase-2 tree: **63 JavaScript tests passed**, **111 Python tests passed**, static build and `git diff --check` passed. The 156-file economic baseline remains unchanged. Approved Core+ 50-minute employment remains **1,212,066.713237**, Shanghai share **37.6335253%**, with original stored precision intact. No current economic result is recalculated from company records.

## Input needed for the first real pilot

Provide a small source export or spreadsheet we can adapt to this raw JSON contract, plus:

1. Stable source IDs/namespace, company name, actual location address, longitude/latitude and confirmed CRS for every usable record. Unknown CRS or missing coordinates will be held for review rather than guessed.
2. Source URLs and short evidence excerpts distinguishing physical offices from registrations; collection/verification dates and which evidence has been reviewed.
3. Any explicitly reviewed Chinese/English entity identities and, where available, physical-office identities. Supply distinct addresses/suites for multiple offices.
4. Reliable industry codes with coding scheme and source/reviewed mapping evidence; leave unknowns blank.
5. Verified building/campus IDs, names and evidence where available; leave unresolved hubs blank.
6. The chosen pilot scope and confirmation that the source permits the intended export/use and eventual display. No API key is needed for this offline pipeline.

A reasonable first review is 50–200 supplied records from one or two sources. Raw data can then be assessed, ambiguities resolved and only a reviewed candidate proposed for later UI integration. No real companies were acquired in phase 2.

## AMap candidate acquisition and human review

See [the Phase 3A pilot workflow](company-access-amap-pilot.md). Acquisition keeps
unreviewed map records quarantined and uses this pipeline unchanged after human
review. No production inventory is connected.

# Company Access — review scaffold

Phase 2 adds an offline preparation pipeline on the same PR. See [offline ingestion, input contract and pilot guide](company-access-ingestion.md). Phase-1 schema/UI constraints below remain in force; the browser still loads no company inventory.

Review base: `83bf441` on `FelixVVu/jinke/main`. No company inventory, production deployment, replacement application, dependency additions, or analytical recalculation is part of this change.

## 1. Structure and existing architecture

The repository is a dependency-free, native JavaScript static application (not React). `scripts/build.mjs` copies `web/src` and `web/public/data`; `main.js` owns the MapLibre map, selected reach, desktop panel and mobile bottom sheet. `office-employment.js` validates the approved estimates; `office-density-display.geojson` is display-only. `StyleSwitchCoordinator` in `map-utils.js` restores overlays after style replacement. Existing code/data in those analytical modules stays unchanged.

| Path | Responsibility |
| --- | --- |
| `web/src/company-access/schema.js` | Exported JSON Schema, canonical office validator, normalization, disclosure |
| `web/src/company-access/model.js` | Reach validation, point membership, independent office/hub/summary/metadata outputs and reconciliation validator |
| `web/src/company-access/layers.js` | MapLibre GeoJSON source and circle layer lifecycle |
| `web/src/company-access/panel.js` | Shared desktop/mobile panel markup and unloaded/ready states |
| `web/src/main.js` | Small integration points in panel, controls and existing style restoration |
| `tests/company-access.test.mjs` | Contract, geometry, summaries, lifecycle and economic regression tests |
| `tests/fixtures/company-access-economic-baseline.json` | SHA-256 baseline of 156 existing data/model files |
| `docs/company-access.md` | Architecture and data contract |

No company files are placed in `web/public/data` yet. Anonymous synthetic records only exist inside test code, which the build does not ship.

## 2. Canonical company-office schema (v1)

Each record represents **one physical company office**, not a company legal entity, employee, job estimate, or arbitrary business POI. Every field below is required as a key; nullable fields must explicitly use `null`. Extra fields (including employment) fail validation.

| Field | Type / rule |
| --- | --- |
| `id` | Nonempty stable physical-office ID; globally unique in inventory |
| `company_name` | Nonempty sourced company name |
| `normalized_name` | NFKC, trim, collapse whitespace, lowercase of company name; no fuzzy merge or legal-suffix removal |
| `longitude`, `latitude` | Finite numbers in −180…180 / −90…90, never numeric strings |
| `coordinate_system` | Exactly `WGS84` in canonical inventory and MapLibre outputs |
| `district` | Nonempty sourced district name or null |
| `address` | Nonempty sourced physical-office address |
| `building_name` | Nonempty name or null |
| `hub_id`, `hub_name` | Nonempty stable hub/building key and name, or both null |
| `industry_code`, `sector` | Nonempty source-backed classification or null; unknown never inferred from name |
| `location_confidence` | `verified`, `building`, or `approximate` |
| `source_type` | `company_website`, `building_directory`, `government`, `licensed_poi`, `osm`, or `other` |
| `source_id` | Nonempty source record/document identifier |
| `source_url` | HTTP(S) evidence URL without embedded credentials |
| `verified_at` | Valid UTC ISO timestamp ending in Z or null; required non-null for verified locations |
| `min_reach_minutes` | 10 / 20 / 30 / 40 / 50 / null, checked against current cumulative polygons |

`verified` means the location was checked against evidence, `building` means building-level positioning, and `approximate` means a lower-precision location. Confidence is categorical, not a fabricated probability. A timestamp records verification rather than collection time; provenance must not claim verification merely because an import ran.

Incoming GCJ-02/BD-09 records must be converted in a future ingestion stage, preserving raw coordinates, original CRS, conversion method/version and evidence there. This scaffold rejects them rather than silently interpreting them as WGS84. Global coordinate bounds cannot detect a mislabeled CRS: source review and Shanghai-boundary QA remain necessary before real inventory approval.

Duplicate office IDs and duplicate `(source_type, source_id, longitude, latitude)` fail. Repeated normalized names are flagged, not automatically collapsed: one company may have several offices, and different companies may share a name. No distinct-company statistic is offered without a stronger identity model. Hub membership is assigned by explicit ID, never proximity or text alone; conflicting names for one hub ID fail.

### Reach semantics

Use **original cumulative `reach-areas.geojson`**, not display bands, heatmap pixels, inverse polygons, station distance or interpolated circles. All five polygons are required. Point inclusion reuses `pointInGeoJson` and handles Polygon, MultiPolygon, holes and boundaries (including hole boundaries). The first containing polygon determines `min_reach_minutes`; null means none contain it, not unverified or missing coordinates.

Derived office properties additionally contain `reach_minutes`, the exact containing limits. Reach filtering uses that list, not `min_reach_minutes <= selection`, because cumulative source polygons may have non-nested slivers. Metadata flags such records. **All** uses actual 50-minute membership, consistent with the app's existing active-limit convention. No geometry is repaired or rewritten.

## 3. Four separate derived outputs

`deriveCompanyAccess(offices, areas, provenance)` returns these independently serializable artifacts. Suggested future filenames below are contracts, not populated datasets in this PR.

| Output / future file | Contents |
| --- | --- |
| `offices` / `company-offices.geojson` | Point FeatureCollection; feature ID = office ID; properties retain every canonical field plus exact `reach_minutes` |
| `hubs` / `company-hubs.geojson` | Point FeatureCollection with hub ID/name, sorted office IDs, total office count and `counts_by_reach` for each limit |
| `summary` / `company-reach-summary.json` | Unit `company_offices`, availability status, five rows of `limit_minutes`, `office_count`, `hub_count`, `unassigned_hub_office_count` |
| `metadata` / `company-access-metadata.json` | Schema/dataset versions, input inventory and reach SHA-256, CRS, source counts, coverage/disclosure, boundary policy, quality flags |

Hubs use the first stable member office's coordinate as an explicitly identified representative point (`representative_office_id`), **not a measured centroid**. Reach counts come from individual offices, never the hub representative position. Offices with null hubs remain in office totals and are counted separately. Hub counts are known hubs containing at least one selected office. Building aggregations use the same explicit hub identity; no speculative building inference occurs.

Metadata includes unverified and approximate counts, offices outside 50 minutes, repeated normalized names, and non-nested membership IDs. No citywide company denominator or completeness percentage is invented. `employment_estimation_permitted` is always false; coverage is `source_inventory_only`.

Provenance requires `status`, `dataset_version`, `inventory_sha256`, `reach_sha256`. A future ingestion runner must compute those hashes from the exact input bytes, review source licensing, retain source-specific raw evidence and coordinate-conversion audit, and use `validateCompanyAccessOutput` before publication. The validator recomputes all four artifacts against canonical input, rejecting stale counts, geometries, metadata or reach assignment. Hash syntax is validated here; it is not proof that external source evidence is truthful. The phase-2 offline runner computes input hashes and validates candidate outputs. No fetcher, geocoder, crawler or browser import workflow is enabled.

## 4. UI architecture

An expandable **Company Access** section is added inside existing `panelControls`. Desktop uses the current scrolling side panel. Mobile uses the same markup and existing expand/collapse bottom sheet; no competing drawer or duplicate state store is introduced.

Initial state is explicitly **Company-office data has not been connected yet**, with the office toggle disabled. Counts are absent/null, not zero. A genuinely loaded empty inventory can show zero sourced offices. GDP / office-employment selectors and their outputs remain separate; Company Access never becomes an economic metric.

Future validated data can be passed to the existing scaffold's `companyAccessOutput` state and controller, then `applyMapState()`. The layer follows the selected 10/20/30/40/50/All choice. Click/tap selects office text in the shared section and expands the mobile sheet; text is assigned with `textContent`. Hover only changes the cursor. This release contains no actual office points, list/search dataset, hub map mode or source-fetch UI. Rich office details, hub browsing and source links are deferred until a real inventory is approved.

## 5. Style/basemap lifecycle

`restoreCustomLayers → existing sources/layers → applyMapState → CompanyAccessLayers.setState/restore`.

The controller lives with the Map object, outside the disposable style. It stores current inventory, reach limit and visibility. After each replacement style, it idempotently recreates `company-access-offices` and `company-access-circles`, refreshes GeoJSON, and reapplies visibility. It inserts the circles immediately **before `station-circle`**, above the existing density/reach layers while leaving station interactions above them.

It reuses the existing coordinator's `styledata` / `style.load` handling and stale-request filtering; it does not add a competing style listener or wait for remote basemap tiles. Delegated mouseenter/mouseleave/click handlers bind once per controller. `destroy()` removes handlers and only the company layer/source. No DOM markers, map replacement, glyph dependency or basemap-specific logic is added.

Hub aggregation is a separate data output, not MapLibre visual clustering and never an employment input. The existing purple office-density heatmap and its toggle are unchanged.

## 6. Protection and review evidence

`npm run test:frontend` includes new tests and existing frontend/office tests:

- Required fields, types, coordinates/CRS, source URLs, timestamps, normalization and duplicate IDs/source locations.
- Five reach thresholds, null outside reach, exact boundaries, holes, MultiPolygon islands, malformed/missing polygons, stale assignments and non-nested memberships.
- Multiple same-name offices, explicit hub membership, deterministic aggregates, source immutability and reconciliation of all four outputs.
- Not-loaded versus real zero; company counts cannot become employment or citywide coverage.
- Repeated and rapid style replacement, stale style events, restored source/visibility, station layer ordering, handler deduplication and cleanup.
- SHA-256 equality for 156 existing data, economic, reach and supporting model files against the review base.
- Exact stored Core+ 50-minute employment `1212066.7132367718`, which remains **1,212,066.713237** at approved six-decimal precision; share remains **37.6335253%** at approved seven-decimal precision. Existing denominator, Core definition, density provenance and GDP tests remain active.

The baseline is intentionally a review guard. A future approved analytical change must explicitly review any baseline update; Company Access development must not refresh it to conceal altered economic data.

Phase-1 validation: 44 frontend tests passed. Full Python suite: 111 passed after synchronizing two pre-existing stale frontend assertions (also reproduced on unmodified base `83bf441`) with the existing All-reach fill layers and `activeLimit()` variable. Only tests changed for that repair. Static builds pass for both `/jinke/` and `/` base paths. Browser visual QA could not run because the available browser blocked the local preview URL (`ERR_BLOCKED_BY_CLIENT`); mobile layout and real browser style switching are not claimed as visually verified. CI runs the existing Python suite and frontend tests on the PR; the existing workflow excludes PRs from deployment.

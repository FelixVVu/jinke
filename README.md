# Jinke Road Metro + Walk Reach Map

This repository uses one architecture: `pipeline/generate.py` for data generation and the root `package.json` for the MapLibre frontend. Earlier duplicate structures such as `python/jinke_generator`, `web/package.json`, and alternate modular `web/src` implementations should not be merged; keeping them would create two generators and two frontend build roots.

## Directory structure

- `pipeline/generate.py` — strict cache validation, rate-limited ORS generation, and Shapely production export.
- `jinke_colab_generation.ipynb` — fresh-runtime Colab runner with five separately runnable stages.
- `archive/jinke_50min_google_sheet_colab.ipynb` — restored historical 50-minute notebook from commit `1f8a0726af83c81f681f2664088c9d4ccaed4f7a`.
- `web/src/main.js` and `web/src/style.css` — MapLibre app.
- `web/public/data/` — static frontend data.
- `audit_outputs/` — sample/audit outputs and optional ZIP.
- `.github/workflows/pages.yml` — single GitHub Pages workflow.

## Outputs

The frontend reads only static files and never calls ORS:

- `web/public/data/reach-areas.geojson` — one reach feature for each 10/20/30/40/50 minute limit.
- `web/public/data/stations.geojson` — stations with Apple time and coordinates.
- `web/public/data/manifest.json` — data version, limits, source, and `production_data` flag.
- `web/public/data/shanghai-boundary.geojson` — high-detail local Shanghai Municipality boundary used by inverse fill and location filtering.
- `web/public/data/outside-reach-areas.geojson` — five precomputed Shanghai-minus-reach features for 10/20/30/40/50 minutes.
- `web/public/data/shanghai-metro-lines.geojson` — 19 locally stored Shanghai Metro line features for the transit-focused basemap.
- `web/public/data/shanghai-metro-stations.geojson` — locally stored station and interchange points for the transit-focused basemap.
- `MyDrive/Jinke50min/audit_outputs/web-data.zip` — final audited export containing exactly the three frontend data files.

When `manifest.production_data` is false, the frontend shows a non-dismissible warning and the polygons must not be treated as final coverage.

## Shanghai boundary and inverse-area regeneration

`shanghai-boundary.geojson` is prepared from **OpenStreetMap administrative boundary relation 913067**, version 155 (`2026-03-27T14:36:13Z`). The pinned source snapshot was retrieved on **2026-08-07** as WGS84 GeoJSON with a `0.00001`-degree polygon threshold and is committed at `data/shanghai-boundary-osm-r913067-v155.geojson` with SHA-256 `055073cfdba9e1717cfc60626a24cfdd8f93cf0042ce173e97b8ad4b64742969`.

To avoid filling Shanghai's large offshore administrative-water polygon, the preparation step clips that administrative geometry to a pinned `water.class=ocean` mask from the keyless OpenFreeMap/OpenMapTiles vector tiles at zoom 10, tile revision `20260802_080001_pt`. The clipped ocean snapshot is committed at `data/shanghai-ocean-openfreemap-z10-20260802.geojson` with SHA-256 `9465528487f7b07b1782b1e794197ce34ed1366ebb111646f31fceaf28257506`.

The result is deliberately land-focused: it keeps the detailed Shanghai-region component, coast, river mouths, Chongming and the local islands, while removing the visually misleading offshore wedge. Distant disconnected relation components far outside the local Shanghai map/search extent are also excluded so the location-search bounding box does not expand into Anhui or Jiangsu. A topology-preserving `0.00015`-degree display simplification (about 17 metres) removes sub-pixel noise without changing polygon structure. The resulting boundary contains 23 local polygon components and more than 3,500 vertices instead of the former 35-vertex approximation.

OpenStreetMap data is © OpenStreetMap contributors and licensed under the **Open Data Commons Open Database License (ODbL) 1.0**. Attribution and provenance are recorded in the committed GeoJSON. See <https://www.openstreetmap.org/relation/913067> and <https://www.openstreetmap.org/copyright>.

The frontend never downloads the boundary from a remote service. Rebuild the prepared boundary from the pinned source snapshot, then deterministically rebuild the five inverse features with Shapely:

```bash
python scripts/prepare_shanghai_boundary.py
python scripts/generate_outside_reach_areas.py
```

The script refuses missing, duplicate, invalid, empty, or non-polygon limits; verifies that each result stays inside Shanghai; and rejects any positive-area overlap with the matching reach geometry.

## Warm vector and Shanghai transit basemaps

The selector identifiers `apple` and `apple-transit` are retained as required UI labels. Both styles are independent Jinke cartography: they contain no proprietary vendor tiles, map data, logos, private endpoints, or official-status claim.

Both styles use the public OpenFreeMap vector-tile instance with the unmodified OpenMapTiles schema and OpenStreetMap data. OpenFreeMap documents that its public instance requires no registration or API key and permits commercial usage. The style source carries the required OpenFreeMap/OpenMapTiles/OpenStreetMap attribution. See <https://openfreemap.org/> and <https://openfreemap.org/quick_start/>.

The Shanghai Metro topology is committed locally in the two GeoJSON files above. It was derived on **2026-08-05** from `metromancn/MetroMapOpenMiniProgram` at pinned commit `087310aa159d44583cc5fef240466439570dbd62`, file `src/data/sh.js`, under the repository's **MIT License**:

- source: <https://github.com/metromancn/MetroMapOpenMiniProgram/blob/087310aa159d44583cc5fef240466439570dbd62/src/data/sh.js>
- license: <https://github.com/metromancn/MetroMapOpenMiniProgram/blob/087310aa159d44583cc5fef240466439570dbd62/LICENSE>

The static dataset includes urban metro lines 1–18 and Pujiang Line. Source GCJ-02 coordinates were converted to WGS84; line geometry connects stations in service order and is intended for cartographic display, not surveyed track alignment. Lines 1–18 use the recognizable colors from `@kyuri-metro/shmetro-palette` 0.1.1 (published 2026-05-04, MIT); Pujiang Line retains the network dataset color. The GeoJSON top-level metadata records the source, date, license, derivation, and palette provenance. No metro data is fetched at runtime.

## Local frontend development

```bash
npm ci
npm run dev
```

Build the static GitHub Pages site with base path `/jinke/`:

```bash
npm run build
```

## Colab ORS-key setup and runner

Open `jinke_colab_generation.ipynb` directly in Colab and run its labelled stages in order:

1. **setup** — clone/update this repository, install dependencies, mount Drive, load `ORS_API_KEY` from Colab Secrets, and create the new cache directory;
2. **dry run** — validate the legacy 50-minute cache and estimate missing calls without contacting ORS;
3. **five-call smoke test** — explicit `RUN_ORS=True` opt-in with an actual HTTP-call budget of five;
4. **full lower-limit run** — explicit `RUN_ORS=True` opt-in with the default 200-call budget;
5. **validation and export** — make no ORS calls, validate completeness, create the five Shapely unions, and write the ZIP.

Do not use Colab's **Run all** command. The notebook states exactly which single line to change and which cell to run for each live stage.

## Dry-run request estimation

Dry run is enabled by default and does not call ORS. In Colab it reads the completed legacy cache from `MyDrive/Jinke50min/ors_cache_50min/`, including readable names such as `金科路_3000s.json`:

```bash
python -m pipeline.generate
```

Expected production Sheet counts are approximately 4 stations below 10 minutes, 12 below 20, 42 below 30, 115 below 40, and 175 below 50. With the completed legacy cache, the expected dry-run result is approximately 175 accepted legacy files and 173 new lower-limit requests. Counts may change when the Sheet changes.

## Test-mode data generation

Use fixture Apple times for non-network tests and demos:

```bash
TEST_MODE=1 python -m pipeline.generate
```

Do not report fixture estimates as production estimates.

## Full data generation

Only after reviewing the dry-run estimate, explicitly opt in from Colab by setting `RUN_ORS=True` in the notebook cell. Shell equivalent:

```bash
RUN_ORS=true ORS_API_KEY="$ORS_API_KEY" MAX_ORS_CALLS=200 python -m pipeline.generate
```

The default cap is 200 actual ORS HTTP calls, the request interval is at least 3.5 seconds, and 429/temporary server failures use retry with backoff. Stop and resume by rerunning; completed requests remain cached in `MyDrive/Jinke50min/ors_cache_multilimit_v1/`.

## Cache reuse and legacy 50-minute cache validation

Cache validation includes station, longitude, latitude, walking seconds, selected limit, and data version for new cache keys. The generator reads 50-minute files only from `ors_cache_50min/`, never writes to that directory, and never schedules 50-minute ORS replacement calls. It stops before any ORS call if the legacy set is absent, close to zero, incomplete, or invalid.

New ORS responses are written only to `ors_cache_multilimit_v1/`. Production export has no circle fallback and no bounding-box union: every cached feature and every final `Polygon`/`MultiPolygon` union is validated with Shapely. `production_data` is set to `true` only after all required caches and all five layers pass validation.

## Exporting the web-data ZIP

After generation, download `MyDrive/Jinke50min/audit_outputs/web-data.zip` from Colab or use `audit_outputs/web-data.zip` locally.

## Placing generated files in `web/public/data`

Copy or unzip the three static files into:

```text
web/public/data/reach-areas.geojson
web/public/data/stations.geojson
web/public/data/manifest.json
```

## Running tests

```bash
python -m pytest -q
npm ci
npm run build
```

## Deploying GitHub Pages

The workflow in `.github/workflows/pages.yml` runs `npm ci`, Python tests, and `npm run build`, then deploys `dist` to GitHub Pages. Configure Pages to use GitHub Actions. The build uses the repository base path `/jinke/`.

## Updating the Google Sheet

Keep the Sheet public or accessible as CSV. Required columns remain:

- `ID`
- `station`
- `apple`

## Regenerating after transit-time or coordinate changes

Rerun the dry-run estimate first. Boundary stations where `apple == limit` are kept as points and do not request zero-second polygons. Station/coordinate/time changes affect the request estimate and modern cache validation.

## ORS quota precautions

- Dry-run is default.
- `RUN_ORS=true` is required for real requests.
- Browser code, tests, GitHub Pages, and Codex must not call ORS.
- Review the missing request estimate before execution.
- Keep `MAX_ORS_CALLS` below your daily quota.
- Multi-range ORS support has not been live-verified or enabled; this implementation uses the one-range fallback.

## Basemap provider configuration

- Existing no-key light/dark/monochrome styles use public OpenStreetMap/CARTO raster tiles subject to provider fair-use policies.
- Satellite uses Esri World Imagery tiles; review Esri licensing, attribution, and domain restrictions before production use.
- Pastel uses the official keyless CARTO Voyager raster basemap with OpenStreetMap and CARTO attribution.
- The two warm vector styles use OpenFreeMap/OpenMapTiles/OpenStreetMap with source attribution embedded in each MapLibre style.
- The transit-focused style reads only the two locally committed MIT-licensed metro GeoJSON files.

## Shanghai location search configuration

General place search is separate from station search and uses MapTiler Search/Geocoding only. The browser reads one runtime value, `window.JINKE_MAPTILER_KEY`, from `runtime-config.js`; the committed default is empty so deployments can supply their existing browser key without copying it into application or basemap code. The key is never written to localStorage or logs and is not used by any basemap.

Requests use the China country filter, the locally computed Shanghai boundary bounding box, Chinese/English language preferences, and proximity to the current map center. Returned coordinates are then checked against the committed `shanghai-boundary.geojson`; results outside Shanghai Municipality are discarded even if the provider returned them.

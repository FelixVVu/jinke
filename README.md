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
- `MyDrive/Jinke50min/audit_outputs/web-data.zip` — final audited export containing exactly the three frontend data files.

Committed GeoJSON is development sample data. When `manifest.production_data` is false, the frontend shows a non-dismissible warning and the polygons must not be treated as final coverage.

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

- No-key defaults for light/dark/monochrome use public OpenStreetMap/CARTO raster tiles subject to provider fair-use policies.
- Satellite uses Esri World Imagery tiles; review Esri licensing, attribution, and domain restrictions before production use.
- Pastel/Stamen Watercolor uses Stadia-hosted tiles and may require a Stadia key/domain configuration for production traffic.
- Apple-inspired labels describe UI/visual treatment only; no Apple Maps data or tiles are used.

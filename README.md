# Jinke Road Metro + Walk Reach Map

This repository uses one architecture: `pipeline/generate.py` for data generation and the root `package.json` for the MapLibre frontend. Earlier duplicate structures such as `python/jinke_generator`, `web/package.json`, and alternate modular `web/src` implementations should not be merged; keeping them would create two generators and two frontend build roots.

## Directory structure

- `pipeline/generate.py` — Colab-safe, one-range fallback ORS generator.
- `jinke_colab_generation.ipynb` — guided Colab runner.
- `web/src/main.js` and `web/src/style.css` — MapLibre app.
- `web/public/data/` — static frontend data.
- `audit_outputs/` — sample/audit outputs and optional ZIP.
- `.github/workflows/pages.yml` — single GitHub Pages workflow.

## Outputs

The frontend reads only static files and never calls ORS:

- `web/public/data/reach-areas.geojson` — one reach feature for each 10/20/30/40/50 minute limit.
- `web/public/data/stations.geojson` — stations with Apple time and coordinates.
- `web/public/data/manifest.json` — data version, limits, source, and `production_data` flag.
- `audit_outputs/reach-areas-full.geojson` and `audit_outputs/web-data.zip` — audit/manual download artifacts outside the optimized web data directory.

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

Open `jinke_colab_generation.ipynb` in Colab. It provides cells to:

1. mount Google Drive;
2. install `requirements.txt`;
3. import `ORS_API_KEY` from Colab Secrets;
4. read the production Google Sheet;
5. use `MyDrive/Jinke50min` for persistent cache/output;
6. run dry-run validation with `RUN_ORS=False`;
7. run an optional five-request smoke test;
8. run complete one-range fallback generation;
9. generate `web-data.zip`.

## Dry-run request estimation

Dry run is enabled by default and does not call ORS:

```bash
python -m pipeline.generate
```

Expected production Sheet counts are approximately 4 stations below 10 minutes, 12 below 20, 42 below 30, 115 below 40, and 175 below 50. Counts may change when the Sheet changes. The current implementation environment could not fetch the Google Sheet because outbound HTTP was blocked with `403 Forbidden`, so production counts must be rechecked in Colab or an unrestricted environment.

## Test-mode data generation

Use fixture Apple times for non-network tests and demos:

```bash
TEST_MODE=1 python -m pipeline.generate
```

Do not report fixture estimates as production estimates.

## Full data generation

Only after reviewing the dry-run estimate, explicitly opt in from Colab by setting `RUN_ORS=True` in the notebook cell. Shell equivalent:

```bash
RUN_ORS=true ORS_API_KEY="$ORS_API_KEY" MAX_ORS_CALLS=450 python -m pipeline.generate
```

The default cap is 450 calls, the request interval is at least 3.5 seconds, and 429/temporary server failures use retry with exponential backoff. Stop and resume by rerunning; completed requests remain cached.

## Cache reuse and legacy 50-minute cache validation

Cache validation includes station, longitude, latitude, walking seconds, and data version for modern cache keys. Legacy 50-minute cache filenames are also checked, and dry-run reports files found, accepted, rejected, rejection reasons, and estimated additional calls. With about 175 valid 50-minute legacy caches, one-range fallback should require about 173 additional requests for the 10/20/30/40-minute layers and should not silently regenerate 50-minute polygons.

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

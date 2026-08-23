# Office-employment spatial framework

This directory contains the review-stage 100 m allocation framework for the
separate office-employment workstream. It does not intersect a reach polygon or
calculate a reach percentage.

## Reproduce

The committed derived OSM building-function evidence makes the normal rerun
self-contained:

```bash
python scripts/run_office_employment_spatial.py --repository-root .
```

To rebuild the building evidence itself, supply the exact 23 August 2026
Shanghai OSM PBF whose SHA-256 is pinned in
`office_employment_pipeline/spatial.py`:

```bash
python scripts/run_office_employment_spatial.py \
  --repository-root . \
  --osm-pbf /absolute/path/to/shanghai-2026-08-23.osm.pbf
```

The public extract URL is rolling, so a later download is expected to fail the
hash gate. The raw PBF is not committed. The derived 100 m evidence is retained
under OpenStreetMap/ODbL attribution.

## Method boundary

- Core I/J/M district×industry totals are official hard controls.
- Core+ Base is central; Low and High retain the reviewed selected-72 district
  composition sensitivity.
- The spatial surface is a deterministic, uncapped evidence allocation. It is
  not PPML and does not use uniform allocation as the main surface.
- The grid covers the eight audited reach-relevant districts inherited from the
  general-employment analytical grid. Other districts remain district controls.
- No GDP, general-employment, reach, station, metro, frontend, or Site file is
  written by this pipeline.

See `outputs/spatial-allocation-report.md` for results, caveats, and the seven
cluster-validation maps.
